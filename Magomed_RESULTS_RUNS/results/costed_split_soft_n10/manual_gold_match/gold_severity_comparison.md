# Gold Severity Comparison (Maschinen-Output)

Quelle der bestätigten IDs: derived from results/costed_split_soft_n10/final_costed_results_summary.json (human_validated_coverage).

| Klasse | Gold total | Confirmed LLM TP (t=0,65) | Coverage (t=0,65) | Confirmed LLM TP (t=0,60) | Coverage (t=0,60) |
|---|---:|---:|---:|---:|---:|
| A | 13 | 1 | 7.69 % | 1 | 7.69 % |
| B | 13 | 1 | 7.69 % | 2 | 15.38 % |
| C | 10 | 1 | 10.00 % | 2 | 20.00 % |
| A+B | 26 | 2 | 7.69 % | 3 | 11.54 % |
| Gesamt | 36 | 3 | 8.33 % | 5 | 13.89 % |

## Bestätigte Gold-IDs je Klasse

- **t = 0,65 (Hauptthreshold):**
  - A: 8
  - B: 31
  - C: 28
- **t = 0,60 (Sensitivität):**
  - A: 8
  - B: 27 31
  - C: 25 28
