# Gold Severity Comparison

## Zweck

Diese Tabelle liefert eine **quantitative Gegenüberstellung der manuell
bestätigten LLM-Gold-Treffer nach Fehlerklasse (A / B / C)** gegen die
Verteilung des Goldstandards. Datenbasis ist
ausschließlich der finale Datensatz `costed_split_soft_n10` (40 Runs:
20 UBR + 20 CBR, je n = 10 Reviewer).

## Datenquellen

- **Goldstandard / Risk-Level:** `artifacts/gold/Faults_List_In_ver6.xls`.
  Der Goldstandard wird mit dem in der Evaluation verwendeten `GoldLoader`
  (`src/fagan_tool/evaluation/gold_loader.py`) geladen — identisch zur
  Evaluations-Pipeline.
- **Bestätigte Gold-IDs (human-validiert):** Die bestätigten
  Goldstandard-IDs werden aus
  `results/costed_split_soft_n10/final_costed_results_summary.json`
  (`human_validated_coverage`) übernommen.

## Methodik (kurz)

1. Goldstandard laden und jeder Gold-ID ihr Risk-Level (A/B/C) zuordnen.
2. Die manuell bestätigten Gold-IDs je Threshold laden
   (t = 0,65 Haupt-, t = 0,60 Sensitivitätsanalyse).
3. Pro Klasse zählen, wie viele bestätigte Treffer (TP) fallen, und die
   Coverage als `bestätigte TP / Gold-Anzahl der Klasse` berechnen.
4. Zusatzzeilen für **A+B** und **Gesamt** bilden.

Die Gold-Verteilung A = 13, B = 13, C = 10 (Σ 36) wird beim Laden reproduziert.

## Tabelle: bestätigte LLM-Coverage nach Severity

| Klasse | Gold total | Confirmed LLM TP (t=0,65) | Coverage (t=0,65) | Confirmed LLM TP (t=0,60) | Coverage (t=0,60) |
|---|---:|---:|---:|---:|---:|
| A | 13 | 1 | 7.69 % | 1 | 7.69 % |
| B | 13 | 1 | 7.69 % | 2 | 15.38 % |
| C | 10 | 1 | 10.00 % | 2 | 20.00 % |
| A+B | 26 | 2 | 7.69 % | 3 | 11.54 % |
| Gesamt | 36 | 3 | 8.33 % | 5 | 13.89 % |

> Coverage = manuell bestätigte LLM-True-Positives in der Klasse geteilt durch
> die Anzahl der Goldfehler dieser Klasse.

## Bestätigte Gold-IDs je Threshold und Klasse

- **t = 0,65 (Hauptthreshold):**
  - A: 8
  - B: 31
  - C: 28
- **t = 0,60 (Sensitivität):**
  - A: 8
  - B: 27 31
  - C: 25 28

## Interpretation

- Die Tabelle zeigt die Verteilung der manuell bestätigten
  Goldstandard-IDs nach den Fehlerklassen A, B und C.
- **t = 0,65 ist der Hauptthreshold.** Maßgeblich sind die dortigen Werte.
- **t = 0,60 ist die Sensitivitätsschwelle** und nicht das primäre
  Ergebnis.
- Die Tabelle aggregiert die manuell bestätigten Treffer nach Severity.
  Sie trifft **keine** Aussage darüber, welche Lesetechnik überlegen ist,
  und ist kein Technikvergleich zwischen UBR und CBR.

## Technische Datengrundlage

- `results/costed_split_soft_n10/manual_gold_match/gold_severity_comparison.csv`
- `results/costed_split_soft_n10/manual_gold_match/gold_severity_comparison.md`
