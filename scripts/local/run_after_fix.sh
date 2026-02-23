#!/usr/bin/env bash
set -euo pipefail

# load env
set -a
source .env
set +a

pytest -q

RUN_ID="thesis_after_matchfix_$(date +%Y%m%d_%H%M%S)"
echo "RUN_ID=$RUN_ID"

fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

python - <<PY
import pandas as pd
from pathlib import Path

run_id = "$RUN_ID"
p = Path("eval")/run_id/"matches_enriched.csv"
df = pd.read_csv(p)
print("\nmatch_type counts:")
print(df["match_type"].value_counts(dropna=False))

hits = df[df["match_type"].isin(["partial","exact"])].copy()
print("\nTop matches:")
if len(hits)==0:
    print("NO MATCHES")
else:
    cols = [c for c in ["match_type","similarity_score","found_position","gold_position","found_description","gold_description"] if c in hits.columns]
    print(hits.sort_values("similarity_score", ascending=False)[cols].head(15).to_string(index=False))
PY

echo "== runs/$RUN_ID =="; ls -lah "runs/$RUN_ID"
echo "== eval/$RUN_ID =="; ls -lah "eval/$RUN_ID"
