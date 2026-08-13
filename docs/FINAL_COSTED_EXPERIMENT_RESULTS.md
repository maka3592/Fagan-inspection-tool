# Finale kostenbezogene Experimentergebnisse — `costed_split_soft_n10`

Dieses Dokument konsolidiert die finalen Ergebnisse der Untersuchung.
Hauptdatensatz ist `costed_split_soft_n10` (40 Runs: 20 UBR + 20 CBR).
Alle Werte stammen direkt aus den Ergebnisdateien unter
`results/costed_split_soft_n10/`. Die supplementäre PBR-Analyse wird aus
`results/costed_pbr_split_soft_n10/` ergänzt. Finale kostenbezogene
Schlussfolgerungen basieren auf `costed_split_soft_n10`.

## 1. Datensatz und experimenteller Aufbau

| Punkt | Wert |
|---|---|
| Datensatz | `costed_split_soft_n10` |
| Runs gesamt | 40 |
| UBR-Runs | 20 |
| CBR-Runs | 20 |
| Reviewer pro Run | 10 (n = 10) |
| Scope | split (soft) |
| Goldstandard | 36 Fehler (A = 13, B = 13, C = 10) |
| Modell | gpt-4o-mini (Temperatur 0.2, max_tokens 4096) |
| Hauptthreshold | 0,65 |
| Sensitivitäts-Threshold | 0,60 |

Für alle betrachteten Runs wurden derselbe Goldstandard und dieselbe
Matching- und Evaluationslogik verwendet. Jeder LLM-Call
protokollierte zusätzlich die reale Token-Nutzung (`response.usage`) und
die technische Ausführungszeit, was die nachfolgende Kostenanalyse erst
ermöglicht.

### Reviewer Budget n=10

n = 10 ist ein **festes Reviewer-Budget** pro Run, identisch für UBR und CBR, und
erlaubt einen fairen UBR-vs-CBR-Vergleich innerhalb desselben Budgets. Es ist
**kein** Optimum und behauptet **keine** vollständige Sättigung: Der
Sättigungspunkt liegt im finalen Datensatz am Budgetende (k\* = N = 10). Die
Inkrementkurven zeigen zudem, dass der zehnte Reviewer noch neue eindeutige
Defekte beitragen kann. Belegbar ist daher nur, dass **im Bereich N ∈ {1..10}
kein Plateau vor dem Budgetende beobachtet** wurde; zusätzliche Reviewer könnten
weitere Defekte liefern, wurden aber nicht ausgeführt. Details:
`docs/REVIEWER_BUDGET_AND_SATURATION.md`.

## 2. Automatische Goldstandard-Coverage

Mit dem bestehenden, textähnlichkeitsbasierten Matcher erreichte die
gepoolte Union aller Reviewer folgende automatische Coverage:

| Threshold | Automatische Union-TP | Recall | Gold-IDs |
|---:|---:|---:|---|
| 0,65 | 5/36 | 13,89 % | 8 28 31 32 38 |
| 0,60 | 9/36 | 25,00 % | 6 7 8 25 27 28 31 32 38 |

Der Anstieg beim niedrigeren Threshold ist thresholdsensitiv und wird
getrennt vom Hauptergebnis berichtet.

## 3. Manuelle Validierung der Gold-Matches

Da das automatische Matching im Wesentlichen über Textähnlichkeit gesteuert
wird, wurde jede automatisch gematchte Gold-ID inhaltlich gegen
Beschreibung, Location, Signal/Entität und Kontext geprüft; reine
Textähnlichkeit wurde nicht als hinreichend für eine Bestätigung
(`confirmed`) gewertet.

**Tabelle: Automatische vs. manuell bestätigte Goldstandard-Coverage**

| Threshold | Automatische TP | Autom. Recall | Bestätigte TP | Bestätigter Recall | Zweifelhaft | Verworfen |
|---:|---:|---:|---:|---:|---|---|
| 0,65 | 5/36 | 13,89 % | 3/36 | 8,33 % | 0 | 32 38 |
| 0,60 | 9/36 | 25,00 % | 5/36 | 13,89 % | 7 | 6 32 38 |

Bestätigte Gold-IDs: `8 28 31` (t = 0,65); `8 25 27 28 31` (t = 0,60).

**Automatisches Textähnlichkeits-Matching überschätzt die bestätigte
Defekterkennung**: Die bestätigte Coverage liegt bei beiden Thresholds
deutlich unter der automatischen Union-TP. Die berichtete Coverage ist
daher stets unter Berücksichtigung der manuellen Validierung zu
interpretieren.

Eine Aufschlüsselung der bestätigten Treffer nach Fehlerklasse (A/B/C, A+B,
Gesamt) findet sich in `docs/GOLD_SEVERITY_COMPARISON.md`.

## 4. API-Token-Nutzung und Kosten

Die API-Kosten sind **aus realer API-Nutzung gemessen** und
**listenpreisbasierte Schätzungen** (offizielle OpenAI-Listenpreise für
gpt-4o-mini, USD) — **keine Rechnungspositionen aus dem Billing-Dashboard**.
Die erfasste technische Laufzeit ist API-/Tool-Ausführungszeit und **kein**
menschlicher Aufwand.

OpenAI-Listenpreise für gpt-4o-mini geprüft am 2026-06-14; verwendete Werte:
0,15 USD Input / 0,60 USD Output je 1 Mio. Tokens (Match mit der offiziellen
OpenAI-Dokumentation; Preisannahmen dokumentiert in `configs/llm_costs.yaml`).

| Metrik | Wert |
|---|---:|
| Gesamt-API-Kosten | 1,465276 USD |
| Tokens gesamt | 8.516.222 |
| Input-Tokens | 8.098.793 |
| Output-Tokens | 417.429 |
| Technische Laufzeit | 5.768,8 s |

**Tabelle: API-Kosten pro automatischem und bestätigtem TP (USD)**

| Threshold | Kosten / automatischem TP (USD) | Kosten / bestätigtem TP (USD) |
|---:|---:|---:|
| 0,65 | 0,293055 | 0,488425 |
| 0,60 | 0,162808 | 0,293055 |

In absoluten Zahlen sind die API-Kosten des gesamten Experiments sehr
niedrig.

## 5. Literaturbasierter Personalkostenkontext

Die Personalkosten sind **literaturbasierte Kontextschätzungen**, **nicht
gemessen** in diesem Experiment. Sie werden in **EUR** berichtet und
**nicht** gegen die USD-API-Kosten verrechnet (keine gemischte
Währungskennzahl). Sie dienen lediglich dazu, die Größenordnung anzudeuten,
vor der die gemessenen API-Kosten gelesen werden können.

**Tabelle: Literaturbasierte Personalkosten-Szenarien (EUR)**

| Szenario | Personenstunden/Defekt | EUR/h | EUR/Defekt | Basis |
|---|---:|---:|---:|---|
| niedrig | 0,8 | 43,40 | 34,72 | Applicon-style lower bound / major problem found and fixed |
| mittel | 1,58 | 43,40 | 68,57 | ICL design-defect effort |
| hoch | 2,7 | 43,40 | 117,18 | Lockheed found-and-fixed upper scenario |

Geschätzte Personalkosten für die bestätigten Goldfehler (nur Kontext, EUR):

| Threshold | Bestätigte TP | niedrig | mittel | hoch |
|---:|---:|---:|---:|---:|
| 0,65 | 3 | 104,16 | 205,71 | 351,54 |
| 0,60 | 5 | 173,60 | 342,85 | 585,90 |

## 6. Technikvergleich und Komplementarität

**Tabelle: UBR vs. CBR vs. UBR ∪ CBR**

| Threshold | Technik | Automatische TP (IDs) | Bestätigte TP (IDs) | API-Kosten (USD) | Kosten / bestätigtem TP (USD) |
|---:|---|---|---|---:|---:|
| 0,65 | UBR | 5 (8 28 31 32 38) | 3 (8 28 31) | 0,740605 | 0,2469 |
| 0,65 | CBR | 4 (8 31 32 38) | 2 (8 31) | 0,724671 | 0,3623 |
| 0,65 | UBR ∪ CBR | 5 (8 28 31 32 38) | 3 (8 28 31) | 1,465276 | 0,4884 |
| 0,60 | UBR | 9 (6 7 8 25 27 28 31 32 38) | 5 (8 25 27 28 31) | 0,740605 | 0,1481 |
| 0,60 | CBR | 6 (7 8 28 31 32 38) | 3 (8 28 31) | 0,724671 | 0,2416 |
| 0,60 | UBR ∪ CBR | 9 (= UBR) | 5 (= UBR) | 1,465276 | 0,2931 |

Token-/Laufzeit-Aufwand je Technik: UBR 4.329.911 Tokens / 2.737,8 s; CBR
4.186.311 Tokens / 3.031,0 s; UBR ∪ CBR 8.516.222 Tokens / 5.768,8 s.

Mengen-Overlap (automatische IDs): CBR ist bei beiden Thresholds eine echte
Teilmenge von UBR (CBR-only = 0); UBR-only = `28` (t = 0,65) und `6 25 27`
(t = 0,60).

- **Im finalen Datensatz enthält CBR keine bestätigten Gold-IDs, die nicht
  bereits durch UBR abgedeckt sind**: CBR ist bei beiden Thresholds eine echte
  Teilmenge von UBR (auf Ebene der automatisch gematchten wie der bestätigten
  Gold-IDs).
- **UBR ∪ CBR verbessert die bestätigte Gold-Coverage gegenüber UBR allein
  nicht**.
- **UBR ∪ CBR ist keine hybride Lesetechnik** — es ist eine nachträgliche
  Ergebnis-Union der technikspezifischen Resultate. Eine eigenständige
  hybride Lesetechnik war nicht Gegenstand der Untersuchung.

### Supplementary PBR Analysis

Zusätzlich zum Hauptvergleich wurde **PBR** (Perspective-Based Reading) im
**selben** instrumentierten Setup getestet (20 Runs, n = 10, gpt-4o-mini,
temperature 0.2, max_tokens 4096, split-soft; Datensatz
`costed_pbr_split_soft_n10`). **PBR ist Supplementary Analysis und nicht Teil des
CBR-/UBR-Hauptvergleichs.** Die automatischen PBR-Kandidaten wurden
mit derselben Matching-Logik erzeugt und anschließend **manuell validiert**.

Ergebnis:
- confirmed PBR-IDs: **8**
- **keine neuen bestätigten PBR-only Gold-IDs** gegenüber UBR/CBR
  (ID 8 ist bereits in der bestätigten UBR/CBR-Menge enthalten)
- PBR **erhöht die bestätigte Coverage gegenüber UBR/CBR nicht**

Interpretation:
- PBR liefert in diesem Setup **keinen belegten Zusatznutzen** für eine
  Technik-Kombination; eine Kombination wäre nur bei zusätzlichen bestätigten
  Defekten gerechtfertigt.
- Dies ist **keine** Aussage, dass PBR generell wirkungslos ist (ein Modell, eine
  Aufgabe, begrenztes Setup).
- Es wurde **keine** hybride Lesetechnik evaluiert; Unionen mit PBR sind post-hoc
  Ergebnis-Merges.

Details: `docs/PBR_SUPPLEMENTARY_MANUAL_VALIDATION_SUMMARY.md` und
`results/costed_pbr_split_soft_n10/`.

### Technique Combination: Post-hoc Union

- `UBR ∪ CBR` und `UBR ∪ CBR ∪ PBR` sind **post-hoc Merges** (nachträgliche
  Ergebnis-Unions), **keine** hybriden Lesetechniken.
- Die geprüften Merges lieferten **keine zusätzlichen bestätigten Gold-IDs**
  gegenüber der bestehenden bestätigten Menge (CBR ⊆ UBR; PBR confirmed = {8},
  bereits enthalten).
- PBR wurde als **Supplementary Analysis** getestet und **manuell validiert**
  (keine neuen bestätigten PBR-only IDs).
- Eine eigenständige hybride Lesetechnik war nicht Gegenstand der
  Untersuchung und ist von den ausgewerteten post-hoc Unions zu
  unterscheiden.
- Details: `docs/TECHNIQUE_COMBINATION_POST_HOC_UNION.md` (post-hoc Union und
  Abgrenzung zur hybriden Lesetechnik).

## 7. Interpretation

- Die automatische Union-TP überzeichnet die Erkennung; nach manueller
  Validierung sind nur 3/36 (t = 0,65) und 5/36 (t = 0,60) Goldfehler
  bestätigt.
- UBR erzielt in diesem Datensatz eine höhere bestätigte Gold-Coverage als
  CBR; CBR liefert in diesem Datensatz keine zusätzlichen bestätigten Gold-IDs
  gegenüber UBR.
- Die nachträgliche Union UBR ∪ CBR verdoppelt die API-Kosten, ohne
  zusätzliche Gold-IDs zu liefern; ihre Kosten pro bestätigtem TP sind daher
  schlechter als die von UBR allein.
- **Niedrige API-Kosten machen zusätzliche Wiederholungen oder
  Technikvarianten wirtschaftlich machbar, niedrige Kosten implizieren
  jedoch keine hohe Inspektionsqualität.** Der begrenzende Faktor ist die
  bestätigte Defektabdeckung, nicht das Budget.

## 8. Bedrohungen der Validität

- **Ein Modell / eine Aufgabe**: ein Modell (gpt-4o-mini) auf einer
  Spezifikation (Taxi). Die Ergebnisse sind möglicherweise nicht
  verallgemeinerbar.
- **Stochastische LLM-Ausgabe**: Unabhängige Runs können leicht
  unterschiedliche Gold-IDs liefern. Die Anzahl ist stabil, die
  Zusammensetzung kann variieren.
- **Manuelle Validierung ist urteilsbasiert**: eine einzige konservative
  Prüfung; `doubtful` wird verwendet, wenn die Evidenz nicht eindeutig ist.
- **Listenpreis-Kostenbasis**: Die Kosten sind listenpreisbasierte
  Schätzungen auf realer Token-Nutzung, keine tatsächlich abgerechneten
  Beträge. Die dokumentierten Preisparameter sind zeitgebunden. Eine
  spätere Neuberechnung mit anderen Preisparametern kann zu anderen
  Kostenwerten führen, während die protokollierten Tokenwerte unverändert
  bleiben.
- **Personalkosten sind externe Literaturschätzungen**, hier nicht gemessen
  und nicht gegen die API-Kosten verrechnet.
- **Matcher-Abhängigkeit**: Die automatische Coverage hängt von der
  textähnlichkeitsbasierten Matching-Logik ab. Die manuelle Prüfung
  mildert diese Abhängigkeit, hebt sie aber nicht auf.

## 9. Einordnung zentraler Fragestellungen

- **Kostenbetrachtung über Defekte pro Stunde hinaus.** Berichtet werden
  reale Token-Nutzung, technische Laufzeit und listenpreisbasierte
  API-Kosten (USD), ergänzt um einen literaturbasierten
  Personalkostenkontext (EUR), der getrennt gehalten wird.
- **Aussagekraft von Textähnlichkeits-Matches.** Die manuelle inhaltliche
  Prüfung reduziert die Coverage von 5 auf 3 (t = 0,65) und von 9 auf 5
  (t = 0,60). Automatische Matches überschätzen die bestätigte Erkennung.
- **Komplementarität von UBR und CBR.** In diesem Datensatz liefert CBR
  keine zusätzlichen bestätigten Gold-IDs gegenüber UBR. Die nachträgliche
  Union UBR ∪ CBR erhöht die bestätigte Gold-Coverage daher nicht und ist
  eine Ergebnis-Union, keine hybride Technik.

## 10. Zentrale Schlussfolgerungen

1. Die bestätigte Gold-Coverage ist niedrig: 3/36 (t = 0,65), 5/36
   (t = 0,60).
2. Automatisches Textähnlichkeits-Matching überschätzt die relevanten
   Treffer.
3. Die gemessenen Gesamt-API-Kosten sind sehr niedrig (≈ 1,47 USD für
   40 Runs; listenpreisbasiert, keine Rechnungspositionen).
4. Im finalen Datensatz enthält CBR keine bestätigten Gold-IDs, die nicht
   bereits durch UBR abgedeckt sind; UBR ∪ CBR (eine nachträgliche Union,
   kein Hybrid) bringt keinen Gewinn an bestätigter Coverage gegenüber UBR
   allein.
5. Niedrige API-Kosten ermöglichen mehr Wiederholungen/Varianten, belegen
   aber für sich genommen keine Inspektionsqualität — diese müsste
   empirisch gezeigt werden.

## 11. Quellenbasis

Externe Quellen für die Kostenbasis und die Kontextwerte.

1. OpenAI. *GPT-4o mini Modell-/API-Preisdokumentation.* Verwendet für die
   listenpreisbasierte API-Kostenberechnung, geprüft am 2026-06-14
   (Input 0,15 USD / Output 0,60 USD je 1 Mio. Tokens).
2. Laitenberger, O., & DeBaud, J.-M. (2000). *An encompassing life cycle
   centric survey of software inspection.* Journal of Systems and Software,
   50(1), 5–31.
3. Statistisches Bundesamt (Destatis). *Eine Arbeitsstunde kostete im Jahr
   2024 durchschnittlich 43,40 Euro.* Pressemitteilung Nr. 154 vom
   30. April 2025.

Die OpenAI-Preisseite stützt die **gemessenen, listenpreisbasierten**
API-Kosten (USD). Der Destatis-Stundensatz und die Aufwandsspannen
(informiert durch Inspektions-Übersichtsliteratur, z. B. Laitenberger &
DeBaud, 2000) stützen den **literaturbasierten Personalkostenkontext**
(EUR); dieser ist rein kontextuell und wurde in diesem Experiment nicht
gemessen.

---

*Für alle Auswertungen wurden der Goldstandard (`artifacts/gold/`) sowie
die Matching- und Evaluationslogik (`src/fagan_tool/evaluation/`)
einheitlich verwendet.*
