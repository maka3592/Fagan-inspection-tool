# Lokale Hilfsskripte

Diese Skripte sind für die lokale Entwicklung und Debugging gedacht.
Sie sind nicht Teil des offiziellen Workflows.

| Skript | Zweck |
|--------|-------|
| `run_4omini.sh` | Test-Run mit gpt-4o-mini |
| `run_gpt5mini.sh` | Test-Run mit gpt-5-mini |
| `run_after_fix.sh` | Test nach Bugfix mit Match-Analyse |
| `verify_run.sh` | Vollständiger Test-Run |

## Verwendung

```bash
cd Fagan_Code
source .env
./scripts/local/run_4omini.sh
```
