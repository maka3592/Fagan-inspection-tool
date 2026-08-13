# Complete Project Structure

## File Tree

```
Fagan_Code/
├── README.md                          # Main documentation
├── ARCHITECTURE.md                    # Technical architecture
├── USAGE_EXAMPLES.md                  # Usage examples and workflows
├── PROJECT_STRUCTURE.md               # This file
├── QUICK_REFERENCE.md                 # Command quick reference
├── LICENSE                            # MIT License
├── .gitignore                         # Git ignore patterns
├── .env.example                       # API key template (no secrets)
│
├── requirements.txt                   # Python dependencies
├── pyproject.toml                     # Modern Python project config
├── pytest.ini                         # Pytest configuration
├── run_example.sh                     # Example run helper (dry-run/ubr/cbr/full)
├── eval_thresholds.sh                 # Multi-threshold evaluation helper
│
├── artifacts/                         # Inspection artifacts
│   ├── input/                         # Input artifacts (SAFE for agents)
│   │   ├── README.md                  # Input artifacts guide
│   │   ├── design/
│   │   │   └── Taxi_des_exp_v2.pdf    # Design document under inspection
│   │   ├── usecases/
│   │   │   ├── UseCasesRank_v3.4.pdf  # Prioritized use cases
│   │   │   └── UseCasesRank_v3.4_extracted.json  # Extracted UBR worklist
│   │   ├── requirements/
│   │   │   └── TextReqSpec_v3.6.pdf   # Requirements specification
│   │   ├── guides/
│   │   │   └── GuideUBR_rankbased_v2.pdf  # UBR reading guide
│   │   └── checklists/
│   │       └── cbr_checklist_v2.yaml  # CBR checklist (CL1-CL7)
│   │
│   └── gold/                          # Gold standard (NEVER for agents!)
│       ├── Faults_List_In_ver6.xls    # 36 reference defects (evaluation only)
│       └── README.md                  # Gold standard guide
│
├── prompts/                           # Agent prompt templates (8)
│   ├── reviewer_ubr.txt               # UBR reviewer prompt
│   ├── reviewer_cbr.txt               # CBR reviewer prompt
│   ├── reviewer_pbr_tester.txt        # PBR Tester perspective
│   ├── reviewer_pbr_designer.txt      # PBR Designer perspective
│   ├── reviewer_pbr_user.txt          # PBR User perspective
│   ├── scribe_meeting.txt             # Scribe consolidation prompt
│   ├── moderator_planning.txt         # Moderator planning prompt
│   └── moderator_followup.txt         # Moderator follow-up prompt
│
├── configs/                           # Configuration files (10)
│   ├── llm_costs.yaml                 # Price assumptions for cost logging
│   ├── examples/                      # Example inspection configs
│   │   ├── c1_ubr.yaml                # Condition 1: UBR
│   │   ├── c1_cbr.yaml                # Condition 1 variant: CBR
│   │   ├── c2_cbr.yaml                # Condition 2: CBR (single reviewer)
│   │   └── c3_pbr_team.yaml           # Condition 3: PBR Team
│   ├── experiments/                   # Final experiment configs
│   │   ├── costed_split_soft_n10_cbr.yaml   # Final: 20 CBR runs (n=10)
│   │   ├── costed_split_soft_n10_ubr.yaml   # Final: 20 UBR runs (n=10)
│   │   ├── costed_pbr_split_soft_n10.yaml   # Final: 20 PBR runs (supplementary)
│   │   └── pbr_same_n10.yaml          # PBR config (loaded by tests)
│   └── checklists/
│       └── cbr_minimal.yaml           # Minimal checklist (used by tests)
│
├── src/fagan_tool/                    # Main source code (26 files)
│   ├── __init__.py                    # Package init
│   ├── cli.py                         # CLI implementation (typer)
│   │
│   ├── core/                          # Core modules
│   │   ├── __init__.py
│   │   ├── schemas.py                 # Pydantic data models
│   │   └── process.py                 # Fagan process orchestration
│   │
│   ├── agents/                        # Agent implementations
│   │   ├── __init__.py
│   │   ├── base_agent.py              # Abstract base agent
│   │   ├── reviewer_agent.py          # Individual inspection
│   │   ├── scribe_agent.py            # Meeting consolidation
│   │   └── moderator_agent.py         # Planning & follow-up
│   │
│   ├── providers/                     # LLM provider abstraction
│   │   ├── __init__.py
│   │   ├── base.py                    # Provider interface
│   │   ├── anthropic_provider.py      # Claude integration
│   │   ├── openai_provider.py         # OpenAI integration
│   │   └── factory.py                 # Provider factory
│   │
│   ├── utils/                         # Utility modules
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py           # PDF text extraction
│   │   ├── artifact_loader.py         # Artifact loading
│   │   ├── leakage_guard.py           # Gold standard protection
│   │   ├── position_tokens.py         # Position/signal token logic
│   │   ├── gold_aligned_filter.py     # Gold-aligned defect subset
│   │   └── usage_logging.py           # Token/cost usage logging
│   │
│   └── evaluation/                    # Evaluation framework
│       ├── __init__.py
│       ├── gold_loader.py             # Gold standard loading
│       ├── matcher.py                 # Defect matching algorithm
│       └── metrics.py                 # Metrics calculation
│
├── tests/                             # Automated unit tests (28 files)
│   ├── __init__.py
│   ├── test_costed_runner_env.py
│   ├── test_defect_report_quality_flags.py
│   ├── test_expected_observed_autofill_fallback.py
│   ├── test_expected_observed_rewrite.py
│   ├── test_fault_share_plots_scope.py
│   ├── test_gold_aligned_filter.py
│   ├── test_gold_loader.py
│   ├── test_json_parse_errors.py
│   ├── test_leakage_guard.py
│   ├── test_manual_validation.py
│   ├── test_matcher.py
│   ├── test_matching_validity.py
│   ├── test_metadata_followup.py
│   ├── test_metrics.py
│   ├── test_no_gold_leakage.py
│   ├── test_openai_provider_tokens.py
│   ├── test_pbr_description_normalization.py
│   ├── test_pbr_position_backfill.py
│   ├── test_position_tokens.py
│   ├── test_process.py
│   ├── test_prompt_snapshot.py
│   ├── test_requirements_artifact.py
│   ├── test_schemas.py
│   ├── test_scribe_validation.py
│   ├── test_threshold_matching.py
│   ├── test_union_gold_coverage_scope.py
│   └── test_usage_logging.py
│
├── scripts/                           # Run/evaluation scripts (23 files)
│   ├── setup.sh                       # Automated setup
│   ├── run_costed_split_soft_n10.py   # Execute final CBR/UBR runs (manifest-driven)
│   ├── run_costed_pbr_split_soft_n10.py  # Execute final PBR runs
│   ├── verify_requirements.py         # Backend of `fagan verify`
│   ├── evaluate_costed_split_soft_n10.py    # Offline evaluation pipeline (main)
│   ├── evaluate_costed_pbr_split_soft_n10.py  # Offline evaluation (PBR)
│   ├── extract_defects_raw.py         # Per-run defect extraction
│   ├── dedupe_analysis.py             # Per-reviewer dedupe/union
│   ├── analyze_overlaps.py            # Reviewer overlap analysis
│   ├── saturation_analysis.py         # Saturation analysis
│   ├── union_gold_coverage.py         # Pooled gold coverage (t=0.65/0.60)
│   ├── gold_at_saturation.py          # Gold coverage at saturation
│   ├── fault_share_plots.py           # Fault share tables/plots
│   ├── manual_gold_match_validation.py  # Rule-based match plausibility layer
│   ├── build_manual_gold_match_review_sheet.py  # Manual review sheet
│   ├── apply_costed_manual_gold_match_decisions.py  # Applies the 14 human decisions
│   ├── build_gold_severity_comparison.py  # Severity comparison
│   ├── analyze_costed_technique_complementarity.py  # Technique overlap
│   ├── compute_requirements_analysis.py  # Derived summaries (derived/)
│   ├── costed_split_soft_n10_cost_per_gold_tp.py  # Cost per gold TP
│   ├── personnel_cost_scenarios_costed_split_soft_n10.py  # Personnel cost scenarios
│   ├── audit_costed_split_soft_n10_usage.py  # Usage/cost aggregation
│   └── extract_use_cases_rankbased.py  # UBR worklist extraction (input prep)
│
├── docs/                              # Documentation (13 markdown files)
│   │                                  # Final results, matching/threshold and
│   │                                  # validation methodology, gold isolation
│   │                                  # proofs, cost/token methodology,
│   │                                  # reviewer budget and PBR supplementary docs
│   └── FINAL_COSTED_EXPERIMENT_RESULTS.md  # Central final results document
│
├── runs/                              # 60 final inspection runs (420 files)
│   ├── costed_cbr_split_soft_n10_001 … _020   # 20 CBR runs
│   ├── costed_ubr_split_soft_n10_001 … _020   # 20 UBR runs
│   └── costed_pbr_split_soft_n10_001 … _020   # 20 PBR runs (supplementary)
│       Each run contains:
│       ├── config_snapshot.json       # Configuration used
│       ├── metadata.json              # Run metadata
│       ├── reviewer_outputs.json      # Individual findings
│       ├── meeting_output.json        # Consolidated findings
│       ├── final_defects.json         # Final defect list
│       ├── final_defects_gold_aligned.json  # Gold-aligned subset
│       └── llm_usage.csv              # Per-call token/cost log
│
├── results/                           # Final result datasets (248 files)
│   ├── README.md                      # Results overview
│   ├── costed_split_soft_n10/         # Main comparison UBR vs. CBR
│   │   ├── final_costed_results_summary.json / final_costed_key_metrics.csv
│   │   ├── evaluation_manifest.csv / costed_baseline_manifest.csv
│   │   ├── raw_defects/ per_reviewer_dedupe/ union_defects/ incremental/
│   │   ├── saturation/ gold_at_saturation/ union_gold_t065/ union_gold_t060/
│   │   ├── manual_gold_match/         # Incl. manual validation decisions
│   │   ├── technique_complementarity/ derived/ costs/ fault_share/
│   ├── costed_pbr_split_soft_n10/     # Supplementary PBR analysis
│   ├── costed_split_soft_n10_manifest.csv (+ _status)
│   ├── costed_pbr_split_soft_n10_manifest.csv (+ _status)
│   └── costed_split_soft_n10_usage_summary.csv / _usage_by_technique.csv
│
└── eval/                              # Evaluation results (generated by fagan eval)
    └── <inspection_id>/
        ├── matches.json               # Match details
        ├── metrics.json               # Performance metrics
        └── report.md                  # Human-readable report
```

## File Categories

### Documentation
- Root: `README.md`, `ARCHITECTURE.md`, `USAGE_EXAMPLES.md`,
  `PROJECT_STRUCTURE.md`, `QUICK_REFERENCE.md`, `LICENSE`
- `docs/` — 13 markdown files (final results, methodology, validation)
- `artifacts/input/README.md`, `artifacts/gold/README.md`, `results/README.md`,
  `results/costed_pbr_split_soft_n10/README.md`

### Configuration (10 YAML files + project config)
- `requirements.txt`, `pyproject.toml`, `pytest.ini`, `.gitignore`, `.env.example`
- `configs/llm_costs.yaml` — price assumptions
- `configs/examples/*.yaml` (4 files) — example configs
- `configs/experiments/*.yaml` (4 files) — final experiment configs + test config
- `configs/checklists/cbr_minimal.yaml` — CBR checklist

### Prompts (8 files)
- `prompts/reviewer_*.txt` (5 files) - Reviewer prompts
- `prompts/scribe_meeting.txt` - Scribe prompt
- `prompts/moderator_*.txt` (2 files) - Moderator prompts

### Source Code (26 files under `src/fagan_tool/`)
Core:
- `core/schemas.py` - Data models
- `core/process.py` - Process orchestration

Agents:
- `agents/base_agent.py`, `agents/reviewer_agent.py`,
  `agents/scribe_agent.py`, `agents/moderator_agent.py`

Providers:
- `providers/base.py`, `providers/anthropic_provider.py`,
  `providers/openai_provider.py`, `providers/factory.py`

Utils:
- `utils/pdf_extractor.py`, `utils/artifact_loader.py`,
  `utils/leakage_guard.py`, `utils/position_tokens.py`,
  `utils/gold_aligned_filter.py`, `utils/usage_logging.py`

Evaluation:
- `evaluation/gold_loader.py`, `evaluation/matcher.py`, `evaluation/metrics.py`

CLI:
- `cli.py` - Command-line interface

### Tests (28 files)
Automated unit tests covering schemas, leakage protection, matching and
thresholds, metrics, scribe consolidation, process orchestration, usage
logging, prompt snapshots, JSON parsing, manual validation and more
(see tree above for the full list).

### Scripts (23 files)
Run execution, offline evaluation pipeline, manual-validation tooling,
cost/usage aggregation and input preparation (see tree above).

## Key Metrics (current inventory)

- **Python Modules (src)**: 26
- **Prompt Templates**: 8
- **Configuration Files (configs/)**: 10
- **Test Files**: 28
- **Scripts**: 23
- **Final Runs**: 60 (20 CBR, 20 UBR, 20 PBR) with 420 files
- **Result Files**: 248

## Module Dependencies

```
cli.py
├── core.process
│   ├── core.schemas
│   ├── agents.*
│   │   └── providers.*
│   ├── utils.*
│   └── evaluation.* (for eval command)
└── evaluation.*
    └── core.schemas
```

## Entry Points

### CLI Entry Points (7 commands)
1. `fagan run` - Run inspection
2. `fagan eval` - Evaluate results
3. `fagan report` - Generate report
4. `fagan dry-run` - Test without API
5. `fagan verify` - Check requirements
6. `fagan manual-template` - Export manual validation CSV
7. `fagan manual-eval` - Metrics from manual annotation

### Programmatic Entry Points
```python
# Main process
from fagan_tool.core.process import FaganProcess

# Evaluation
from fagan_tool.evaluation import DefectMatcher, GoldLoader, MetricsCalculator

# Agents (if extending)
from fagan_tool.agents import ReviewerAgent, ScribeAgent, ModeratorAgent

# Providers (if adding new)
from fagan_tool.providers import get_provider
```

## Generated Directories

These directories are created during execution:

- `runs/<inspection_id>/` - Per-run outputs (new runs; the 60 final runs are part of the project)
- `eval/<inspection_id>/` - Per-run evaluation
- `.venv/` - Virtual environment (if created)
- `__pycache__/` - Python bytecode cache

## Critical Files for Research

### Must Have (Input)
1. `artifacts/input/design/*.pdf` - Design documents
2. `artifacts/input/usecases/*.pdf` - Use cases
3. `artifacts/gold/*.xls` - Gold standard
4. `configs/experiments/costed_*.yaml` - Final configurations

### Must Review (Output)
1. `results/costed_split_soft_n10/` - Final main-comparison results
2. `results/costed_pbr_split_soft_n10/` - Supplementary PBR results
3. `runs/*/final_defects.json` - Found defects per run
4. `docs/FINAL_COSTED_EXPERIMENT_RESULTS.md` - Final results document

## Customization Points

1. **Prompts**: Edit files in `prompts/` to adjust agent behavior
2. **Configs**: Create new YAML files in `configs/examples/`
3. **Checklists**: Add custom checklists in `configs/checklists/`
4. **Providers**: Add new LLM providers in `src/fagan_tool/providers/`
5. **Reading Techniques**: Extend in `schemas.py` + new prompt

## Development Workflow

1. Edit source in `src/fagan_tool/`
2. Update tests in `tests/`
3. Run tests: `pytest tests/`
4. Update docs if needed
5. Test with `fagan dry-run`
6. Run real inspection
7. Evaluate and review results
