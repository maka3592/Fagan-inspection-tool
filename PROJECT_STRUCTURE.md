# Complete Project Structure

## File Tree

```
Fagan_Code/
├── README.md                          # Main documentation
├── ARCHITECTURE.md                    # Technical architecture
├── USAGE_EXAMPLES.md                  # Usage examples and workflows
├── PROJECT_STRUCTURE.md               # This file
├── LICENSE                            # MIT License
├── .gitignore                         # Git ignore patterns
│
├── requirements.txt                   # Python dependencies
├── pyproject.toml                     # Modern Python project config
├── pytest.ini                         # Pytest configuration
│
├── artifacts/                         # Inspection artifacts
│   ├── input/                         # Input artifacts (SAFE for agents)
│   │   ├── README.md                  # Input artifacts guide
│   │   ├── design/                    # Design documents
│   │   ├── usecases/                  # Use case specifications
│   │   ├── requirements/              # Requirements documents
│   │   └── guides/                    # Reading technique guides
│   │
│   └── gold/                          # Gold standard (NEVER for agents!)
│       └── README.md                  # Gold standard guide
│
├── prompts/                           # Agent prompt templates
│   ├── reviewer_ubr.txt               # UBR reviewer prompt
│   ├── reviewer_cbr.txt               # CBR reviewer prompt
│   ├── reviewer_pbr_tester.txt        # PBR Tester perspective
│   ├── reviewer_pbr_designer.txt      # PBR Designer perspective
│   ├── reviewer_pbr_user.txt          # PBR User perspective
│   ├── scribe_meeting.txt             # Scribe consolidation prompt
│   ├── moderator_planning.txt         # Moderator planning prompt
│   └── moderator_followup.txt         # Moderator follow-up prompt
│
├── configs/                           # Configuration files
│   ├── examples/                      # Example inspection configs
│   │   ├── c1_ubr.yaml                # Condition 1: UBR
│   │   ├── c2_cbr.yaml                # Condition 2: CBR
│   │   ├── c3_pbr_team.yaml           # Condition 3: PBR Team
│   │   └── c4_hybrid.yaml             # Condition 4: Hybrid
│   │
│   └── checklists/                    # CBR checklists
│       └── cbr_minimal.yaml           # Minimal checklist
│
├── src/fagan_tool/                    # Main source code
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
│   │   └── leakage_guard.py           # Gold standard protection
│   │
│   └── evaluation/                    # Evaluation framework
│       ├── __init__.py
│       ├── gold_loader.py             # Gold standard loading
│       ├── matcher.py                 # Defect matching algorithm
│       └── metrics.py                 # Metrics calculation
│
├── tests/                             # Unit tests
│   ├── __init__.py
│   ├── test_schemas.py                # Schema tests
│   ├── test_leakage_guard.py          # Leakage protection tests
│   └── test_matcher.py                # Matching algorithm tests
│
├── scripts/                           # Helper scripts
│   └── setup.sh                       # Setup script
│
├── runs/                              # Inspection run outputs (generated)
│   └── <inspection_id>/
│       ├── config_snapshot.json       # Configuration used
│       ├── metadata.json              # Run metadata
│       ├── reviewer_outputs.json      # Individual findings
│       ├── meeting_output.json        # Consolidated findings
│       └── final_defects.json         # Final defect list
│
└── eval/                              # Evaluation results (generated)
    └── <inspection_id>/
        ├── matches.json               # Match details
        ├── metrics.json               # Performance metrics
        └── report.md                  # Human-readable report
```

## File Categories

### Documentation (8 files)
- `README.md` - Main project documentation
- `ARCHITECTURE.md` - Technical architecture details
- `USAGE_EXAMPLES.md` - Usage examples and workflows
- `PROJECT_STRUCTURE.md` - This file
- `artifacts/input/README.md` - Input artifacts guide
- `artifacts/gold/README.md` - Gold standard guide
- `LICENSE` - MIT License

### Configuration (9 files)
- `requirements.txt` - Python dependencies
- `pyproject.toml` - Modern Python project config
- `pytest.ini` - Test configuration
- `.gitignore` - Git ignore patterns
- `configs/examples/*.yaml` (4 files) - Example configs
- `configs/checklists/cbr_minimal.yaml` - CBR checklist

### Prompts (8 files)
- `prompts/reviewer_*.txt` (5 files) - Reviewer prompts
- `prompts/scribe_meeting.txt` - Scribe prompt
- `prompts/moderator_*.txt` (2 files) - Moderator prompts

### Source Code (23 files)
Core:
- `src/fagan_tool/core/schemas.py` - Data models (400+ lines)
- `src/fagan_tool/core/process.py` - Process orchestration (350+ lines)

Agents:
- `src/fagan_tool/agents/base_agent.py` - Base agent (100+ lines)
- `src/fagan_tool/agents/reviewer_agent.py` - Reviewer (180+ lines)
- `src/fagan_tool/agents/scribe_agent.py` - Scribe (150+ lines)
- `src/fagan_tool/agents/moderator_agent.py` - Moderator (120+ lines)

Providers:
- `src/fagan_tool/providers/base.py` - Interface (40 lines)
- `src/fagan_tool/providers/anthropic_provider.py` - Claude (60 lines)
- `src/fagan_tool/providers/openai_provider.py` - OpenAI (60 lines)
- `src/fagan_tool/providers/factory.py` - Factory (50 lines)

Utils:
- `src/fagan_tool/utils/pdf_extractor.py` - PDF handling (130 lines)
- `src/fagan_tool/utils/artifact_loader.py` - Artifact loading (130 lines)
- `src/fagan_tool/utils/leakage_guard.py` - Protection (60 lines)

Evaluation:
- `src/fagan_tool/evaluation/gold_loader.py` - Gold loading (120 lines)
- `src/fagan_tool/evaluation/matcher.py` - Matching (200+ lines)
- `src/fagan_tool/evaluation/metrics.py` - Metrics (100 lines)

CLI:
- `src/fagan_tool/cli.py` - Command-line interface (300+ lines)

### Tests (4 files)
- `tests/test_schemas.py` - Data model tests
- `tests/test_leakage_guard.py` - Security tests
- `tests/test_matcher.py` - Matching tests

### Scripts (1 file)
- `scripts/setup.sh` - Automated setup

## Line Count Summary

```
Language                     files          blank        comment           code
---------------------------------------------------------------------------------
Python                          23            800            450           3500
Markdown                         8            200              0           1500
YAML                             5             20             10            200
Text (Prompts)                   8             50             20            400
Shell                            1             10              5             50
TOML/INI                         2             10              5             80
---------------------------------------------------------------------------------
TOTAL                           47           1090            490           5730
```

## Key Metrics

- **Total Files**: 47 (excluding generated outputs)
- **Python Modules**: 23
- **Prompt Templates**: 8
- **Configuration Files**: 9
- **Documentation Files**: 8
- **Test Files**: 4

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

### CLI Entry Points (4 commands)
1. `fagan run` - Run inspection
2. `fagan eval` - Evaluate results
3. `fagan report` - Generate report
4. `fagan dry-run` - Test without API

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

- `runs/<inspection_id>/` - Per-run outputs
- `eval/<inspection_id>/` - Per-run evaluation
- `.venv/` - Virtual environment (if using setup.sh)
- `__pycache__/` - Python bytecode cache

## Critical Files for Research

### Must Have (Input)
1. `artifacts/input/design/*.pdf` - Design documents
2. `artifacts/input/usecases/*.pdf` - Use cases
3. `artifacts/gold/*.xls` - Gold standard
4. `configs/examples/*.yaml` - Configuration

### Must Review (Output)
1. `runs/*/final_defects.json` - Found defects
2. `eval/*/metrics.json` - Performance metrics
3. `eval/*/matches.json` - Match details
4. `eval/*/report.md` - Human-readable report

## Customization Points

1. **Prompts**: Edit files in `prompts/` to adjust agent behavior
2. **Configs**: Create new YAML files in `configs/examples/`
3. **Checklists**: Add custom checklists in `configs/checklists/`
4. **Providers**: Add new LLM providers in `src/fagan_tool/providers/`
5. **Reading Techniques**: Extend in `schemas.py` + new prompt

## Version Control Strategy

### Tracked
- All source code
- Documentation
- Configurations
- Tests
- Prompts

### Not Tracked (.gitignore)
- `__pycache__/`
- `.venv/`
- `runs/` (optional - configure per project)
- `eval/` (optional - configure per project)
- `artifacts/gold/*.xls` (sensitive data)
- API keys and secrets
- `.DS_Store`

## Installation Footprint

After installation:
```
Fagan_Code/
├── [All project files]      ~5.7k lines of code
├── .venv/                     ~200 MB (dependencies)
├── __pycache__/              ~5 MB (bytecode)
└── runs/ + eval/             Variable (per run)
```

## Development Workflow

1. Edit source in `src/fagan_tool/`
2. Update tests in `tests/`
3. Run tests: `pytest tests/`
4. Update docs if needed
5. Test with `fagan dry-run`
6. Run real inspection
7. Evaluate and review results

## Deployment Checklist

✓ Requirements installed
✓ API key configured
✓ Artifacts placed in `artifacts/input/`
✓ Gold standard in `artifacts/gold/`
✓ Config files customized
✓ Tests passing
✓ Dry-run successful
