# Reviewer Budget n=10 and Saturation (Confirmed Gold IDs)

Diese Analyse adressiert das Feedback zu n=10 **datenbasiert**: Sie zeigt
inkrementell, wie sich die **bestätigte** Goldstandard-Abdeckung mit steigender
Revieweranzahl entwickelt. Reproduzierbar über
`scripts/compute_requirements_analysis.py`; Rohwerte in
`results/costed_split_soft_n10/derived/reviewer_incremental_gain.csv`.

## Motivation für n=10

- Die Zahl n=10 wird **nicht** als empirisch optimale Reviewerzahl eingeführt.
- **n=10 wurde als festes experimentelles Budget gewählt.**
- Im split-soft Setup ist der Reviewer-Index ein **Sektionsanker**; dadurch
  **deckt n=10 die definierten Sektionsanker des inspizierten Artefakts ab**.
- Das Budget begrenzt zugleich den API-Aufwand, die Anzahl der Modelloutputs und
  den manuellen Validierungsaufwand.
- Die nachfolgende inkrementelle Analyse prüft, **ob innerhalb dieses Budgets
  eine Sättigung sichtbar wird**.
- Ist keine stabile Sättigung erkennbar, wird die Begrenzung auf n=10 als
  **Limitation der Studie** behandelt.

## Methode (kurz)

- Betrachtet werden die **manuell bestätigten** Gold-IDs (nicht die automatischen
  Kandidaten): t=0,65 → `8 28 31`; t=0,60 → `8 25 27 28 31`.
- Für Reviewer-Budget k = 1…10 werden alle Reviewer mit Index ≤ k (gepoolt über
  alle 20 Runs der Technik) genommen, ihre Defekte mit dem kanonischen Matcher
  gegen den Goldstandard gematcht und mit der bestätigten Menge geschnitten.
- **Wichtige Einschränkung:** Der Reviewer-Index ist bei split-soft ein
  **Sektionsanker** (Reviewer 1 = Abschnitt 3.1 … Reviewer 10 = Table 1), keine
  zufällige Reviewer-Reihenfolge. Die inkrementelle Kurve spiegelt damit die
  Reihenfolge der Sektionsabdeckung wider, nicht beliebige Reviewer-Redundanz.

## Ergebnis: inkrementelle bestätigte Coverage (UBR ∪ CBR)

| Reviewer-Budget k | t=0,65: kumuliert (IDs) | neu bei k | t=0,60: kumuliert (IDs) | neu bei k |
|---:|---|---:|---|---:|
| 1 | 8 | +1 | 8 25 | +2 |
| 2 | 8 31 | +1 | 8 25 31 | +1 |
| 3 | 8 31 | 0 | 8 25 31 | 0 |
| 4 | 8 31 | 0 | 8 25 31 | 0 |
| 5 | 8 31 | 0 | 8 25 27 31 | +1 |
| 6 | 8 31 | 0 | 8 25 27 31 | 0 |
| 7 | 8 31 | 0 | 8 25 27 31 | 0 |
| 8 | 8 31 | 0 | **8 25 27 28 31** | **+1** |
| 9 | **8 28 31** | **+1** | 8 25 27 28 31 | 0 |
| 10 | 8 28 31 | **0** | 8 25 27 28 31 | **0** |

(Pro Einzeltechnik siehe `reviewer_incremental_gain.csv`; UBR erreicht die volle
bestätigte Menge, CBR bleibt eine Teilmenge.)

## Interpretation

- **Der 10. Reviewer fügt keine neue bestätigte Gold-ID hinzu** (beide
  Thresholds, alle Scopes: `new_confirmed_added` bei k=10 = 0).
- **Aber:** Die bestätigte Coverage steigt **bis spät** an — die letzte neue
  bestätigte ID kommt erst bei **Reviewer 9** (t=0,65, ID 28) bzw. **Reviewer 8**
  (t=0,60, ID 28) hinzu.
- Daraus folgt: Es gibt **keine frühe Sättigung** innerhalb des Budgets. Ein
  Plateau ist allenfalls am **Ende** des Budgets (Schritt 9→10 bzw. 8→10) zu
  beobachten.

## Schlussfolgerung für die Arbeit

- **n=10 ist methodisch motiviert durch das feste Budget und die Abdeckung der
  Sektionsanker, aber nicht als Qualitätsoptimum belegt.** Aus den Daten wird
  **keine optimale Reviewerzahl** abgeleitet.
- Die Daten zeigen keine frühe Sättigung; **eine frühe Sättigung kann nicht
  behauptet werden**.
- Da die letzte neue confirmed Gold-ID erst spät hinzukommt (Reviewer 9 bei
  t=0,65, Reviewer 8 bei t=0,60), darf **keine allgemeine Sättigungsgrenze**
  behauptet werden.
- Reviewer 10 bringt zwar keinen zusätzlichen confirmed Treffer; **daraus folgt
  nicht, dass Reviewer 11–15 nichts bringen würden**.
- **Zusätzliche Reviewer über n=10 hinaus wurden nicht untersucht.** Diese
  Nicht-Untersuchung ist eine **Limitation der Studie** und ein möglicher
  Future-Work-Punkt.
- Ergänzend: Eine separate, run-interne Sättigungsanalyse auf **eindeutigen
  Defekten** (nicht gold-bezogen) zeigt bis Reviewer 10 keine Sättigung.
  Beide Sichten stützen dieselbe
  vorsichtige Aussage: n=10 ist ein Budget, kein belegtes Optimum.
- Die Kurve hängt zudem an der **Sektionsanker-Reihenfolge** (split-soft) und an
  der **niedrigen absoluten** bestätigten Coverage (3 bzw. 5 IDs); sie ist nicht
  als allgemeine Aussage über die „richtige" Revieweranzahl zu lesen.
