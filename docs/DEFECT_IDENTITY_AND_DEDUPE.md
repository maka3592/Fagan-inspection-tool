# Defekt-Identität und Dedupe-Analyse

Diese Datei beschreibt, wie Defekte über Reviewer und Runs hinweg
identifiziert und entdoppelt werden. Sie liefert die Datengrundlage für
nachvollziehbare Aussagen wie *"welcher Reviewer hat welchen Defekt
gefunden, und welche Defekte wurden mehrfach gemeldet?"* — ohne den
Gold-Standard zu konsultieren.

Stand: 2026-05-27.

---

## 1. Defekt-Identität (`defect_id`)

Quelle: `scripts/analyze_overlaps.py::defect_identity` — diese Funktion
ist die einzige Definition; `scripts/extract_defects_raw.py` und
`scripts/dedupe_analysis.py` importieren sie direkt, damit Overlap-,
Union- und Dedupe-Auswertungen exakt dieselbe Identität verwenden.

**Regel:**

1. Falls das Defekt-Objekt einen expliziten `defect_id`-Schlüssel
   mitbringt: `id = "explicit:<value>"`.
2. Sonst: SHA1 (16-Hex-Präfix) über die normalisierte Tupel-Repräsentation
   ```
   fault_type | description_norm | position_norm | page_hint_norm
   ```
   ergibt `id = "h:<16-hex>"`.

**Position-Reihenfolge:** Es wird der erste vorhandene Wert aus
`position_canonical`, `position`, `original_position` verwendet.

**Normalisierung:** lowercase, Satzzeichen → Leerzeichen, mehrfaches
Whitespace zu einem Space kollabiert, getrimmt.

**Bewusst nicht verwendet:** die reviewer-lokale `id`
(z. B. `reviewer_1_ubr_c4111bbf`) — sie ist pro Reviewer einzigartig
und würde Overlap immer null werden lassen.

---

## 2. Warum Dedupe nötig ist

Pro Inspektions-Run laufen N Reviewer (1, 2, 3, 5 oder 10) parallel auf
denselben Artefakten (`scope_mode = same`). Aussagen wie *"das Team hat
X Defekte gefunden"* oder *"Effekt der Reviewer-Anzahl auf Coverage"*
sind nur sinnvoll, wenn Mehrfachmeldungen zwischen Reviewern
entdoppelt werden. Innerhalb eines Reviewers können theoretisch auch
Duplikate auftauchen (gleicher Defekt zweimal beschrieben) — die Stats
weisen das separat aus.

Die `defect_id` ist die einzige Brücke zwischen "die fünf Reviewer
melden den 'Reject_Order'-Defekt" und "im Union-Set zählt der Defekt
genau einmal". Ohne stabile ID gäbe es nur lose Beschreibungen.

---

## 3. Generierte Outputs (Übersicht)

> **Datenbasis:** Der finale Datensatz ist `costed_split_soft_n10`.
> Diese Outputs werden über `scripts/evaluate_costed_split_soft_n10.py`
> erzeugt und liegen unter `results/costed_split_soft_n10/` (Unterordner
> `raw_defects/`, `per_reviewer_dedupe/`, `union_defects/`, `incremental/`).

| Datei (unter `results/costed_split_soft_n10/`)         | Erzeugt von               | Inhalt                                                   |
|--------------------------------------------------------|---------------------------|----------------------------------------------------------|
| `raw_defects/raw_defects_<RUN_ID>.csv`                 | `extract_defects_raw.py`  | flache Tabelle: pro (reviewer, defect) eine Zeile        |
| `per_reviewer_dedupe/per_reviewer_dedupe_<RUN_ID>.csv` | `dedupe_analysis.py`      | within-reviewer Dedupe-Stats                             |
| `union_defects/union_defects_<RUN_ID>.csv`             | `dedupe_analysis.py`      | Union pro `defect_id` + Anzahl Reviewer                  |
| `incremental/incremental_<RUN_ID>.csv`                 | `dedupe_analysis.py`      | k → neue Defekte beim Hinzufügen Reviewer k              |
| `per_reviewer_dedupe/defect_frequency_summary.csv`     | `dedupe_analysis.py`      | Aggregat über (technique, n_reviewers)                   |
| `overlap_<RUN_ID>.csv` (separat, `analyze_overlaps.py`)| `analyze_overlaps.py`     | Pairwise-Jaccard-Matrix über `defect_id` (gleiche Logik) |

### Spalten

`raw_defects_<RUN_ID>.csv`:
`run_id, technique, n_reviewers, reviewer_id, defect_id, fault_type,
position, page_hint, description_raw, description_norm, source, timestamp`

`per_reviewer_dedupe_<RUN_ID>.csv`:
`reviewer_id, total_findings, unique_ids, duplicates, duplicate_ratio`

`union_defects_<RUN_ID>.csv`:
`run_id, defect_id, reviewer_count, reviewer_ids,
representative_fault_type, representative_position,
representative_page_hint, representative_description`
(sortiert nach `reviewer_count desc, defect_id`)

`incremental_<RUN_ID>.csv`:
`k, reviewer_id, new_unique, cumulative_unique`
(Reviewer-Reihenfolge: stabil lexikalisch nach `reviewer_id`)

`defect_frequency_summary.csv`:
`technique, n_reviewers, n_runs, union_unique_mean/median/min/max,
duplicate_ratio_mean, top_defect_ids` (Top-5 nach
Reviewer-Frequenz; `defect_id:count` joined mit `;`)

---

## 4. Bedienung

**Aktiver Datensatz `costed_split_soft_n10`:** Die End-to-End-Auswertung
(inkl. extract/dedupe) wird über den Wrapper erzeugt; er schreibt alle
Outputs nach `results/costed_split_soft_n10/`:

```bash
python scripts/evaluate_costed_split_soft_n10.py
```

Die Einzelschritt-Skripte sind weiterhin direkt aufrufbar (z. B. für einen
einzelnen Run):

```bash
python scripts/extract_defects_raw.py --run-id <RUN_ID> --out-dir results/costed_split_soft_n10/raw_defects
python scripts/dedupe_analysis.py    --run-id <RUN_ID> --out-dir results/costed_split_soft_n10/per_reviewer_dedupe
```

Beide Skripte sind read-only auf `runs/` und schreiben ausschließlich
unter `results/`. `artifacts/gold/` wird nie angefasst.

---

## 5. Grenzen und Fallstricke

- **Semantische Duplikate, lexikalisch unterschiedlich**: zwei Reviewer
  beschreiben denselben Defekt mit anderen Worten oder leicht
  abweichender Position. Sie bekommen unterschiedliche `defect_id`s und
  zählen im Union-Set doppelt. Die Normalisierung deckt nur
  Casing/Whitespace/Punctuation ab — keinen Sinn.
- **Stabilität über Runs**: Die `defect_id` ist deterministisch in
  Bezug auf `(fault_type, description, position, page_hint)`. Wenn der
  LLM in Run A "*'Reject_Order': A signal is missing...*" und in Run B
  exakt denselben String produziert, erhalten beide dieselbe ID — was
  auch tatsächlich auftritt (siehe `top_defect_ids` in
  `defect_frequency_summary.csv`, der Eintrag `h:477ab0e330bb81d0`
  ist über alle N hinweg der häufigste Eintrag in UBR/CBR). Bei abweichender Formulierung
  trennt die ID die Befunde aber als verschieden.
- **`duplicate_ratio` innerhalb eines Reviewers ist in den vorliegenden
  Runs durchweg 0** — der Scribe/LLM dedupliziert je Reviewer-Output
  bereits, sodass `total_findings == unique_ids` gilt. Die Spalte bleibt
  trotzdem im Schema, weil sie zukünftige Regressionsfälle direkt
  aufdecken würde.
- **Kein Gold-Bezug**: Die Outputs treffen keine Aussage darüber, ob ein
  Defekt korrekt ist. Der Abgleich gegen Gold läuft separat über
  `fagan eval` (`eval/<RUN_ID>/`).

---

## 6. Verbindung zum aktiven Datensatz

Datenbasis der finalen Auswertung ist der Datensatz `costed_split_soft_n10`
(40 Runs: 20 UBR + 20 CBR, n = 10). Der Wrapper
`scripts/evaluate_costed_split_soft_n10.py` erzeugt aus den
`runs/costed_*`-Läufen das interne Manifest `costed_baseline_manifest.csv`
und beschränkt darauf Defekt-Identität, Dedupe-Statistik und Reporting-Set —
konsistent zueinander. Die finalen Ergebnisse fasst
`docs/FINAL_COSTED_EXPERIMENT_RESULTS.md` zusammen.
