# Quick Reference Card

## Installation

```bash
# Clone/navigate to project
cd Fagan_Code

# Run setup script
bash scripts/setup.sh

# Or manual:
pip install -r requirements.txt
pip install -e .

# Set API key
export OPENAI_API_KEY="your-key"
```

## Commands

### Run Inspection
```bash
fagan run --config configs/examples/c1_ubr.yaml
```

### Evaluate Results
```bash
fagan eval --run c1_ubr_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
```

### Generate Report
```bash
fagan report --run c1_ubr_run_001
```

### Test Without API (Dry Run)
```bash
fagan dry-run
```

## File Locations

### Input (What You Provide)
- Design docs: `artifacts/input/design/`
- Use cases: `artifacts/input/usecases/`
- Requirements: `artifacts/input/requirements/`
- Gold standard: `artifacts/gold/`
- Configs: `configs/examples/`

### Output (What Tool Generates)
- Run results: `runs/<inspection_id>/`
- Evaluation: `eval/<inspection_id>/`

## Configuration Template

```yaml
inspection_id: "my_run_001"
condition: "C1_UBR"  # C1_UBR, C2_CBR, C3_PBR_TEAM, C4_HYBRID

reading_techniques:
  - "UBR"  # UBR, CBR, PBR_TESTER, PBR_DESIGNER, PBR_USER

artifacts:
  - "design/my_design.pdf"
  - "usecases/my_usecases.pdf"

llm_params:
  provider: "openai"  # openai or anthropic
  model: "gpt-4o-mini"
  temperature: 0.2
  max_tokens: 4096

dry_run: false
```

## Experimental Conditions

| Code | Name | Description |
|------|------|-------------|
| C1 | UBR | Single reviewer, use case traceability |
| C2 | CBR | Single reviewer, systematic checklist |
| C3 | PBR Team | 3 reviewers (Tester, Designer, User) |
| C4 | Hybrid | All techniques combined |

## Defect Schema

```json
{
  "id": "reviewer_1_abc123",
  "position": "Section 3.2",
  "page_hint": "p. 15",
  "risk": "A",           // A=High, B=Medium, C=Low
  "fault_type": "M",     // M=Missing, W=Wrong
  "description": "...",
  "evidence": "...",
  "confidence": 0.9      // 0.0-1.0
}
```

## Metrics Output

```json
{
  "precision": 0.80,     // Of found, how many are real
  "recall": 0.67,        // Of real, how many found
  "f1_score": 0.73,      // Harmonic mean
  "recall_by_risk": {
    "A": 0.75,
    "B": 0.65,
    "C": 0.60
  }
}
```

## Common Tasks

### View Found Defects
```bash
cat runs/<run_id>/final_defects.json | jq
```

### View Metrics
```bash
cat eval/<run_id>/metrics.json | jq
```

### View Meeting Minutes
```bash
cat runs/<run_id>/meeting_output.json | jq '.minutes'
```

### List All Runs
```bash
ls -l runs/
```

### Compare Conditions
```bash
# Run all conditions
for config in configs/examples/*.yaml; do
  fagan run --config $config
done

# Evaluate all
for run in runs/*/; do
  fagan eval --run $(basename $run) --gold artifacts/gold/Faults_List_In_ver6.xls
done

# Compare recalls
cat eval/*/metrics.json | jq '.recall'
```

## Thesis Runs (Recommended)

**Default Model: `gpt-4o-mini`** (stable, fully tested)

### Quick Start

```bash
# Using the run_example script (recommended)
./run_example.sh dry-run   # Test ohne API-Key
./run_example.sh ubr       # UBR-Run + Eval
./run_example.sh cbr       # CBR-Run + Eval
./run_example.sh full      # Kompletter Durchlauf
```

### Manual Run

```bash
# Load environment
set -a; source .env; set +a

# Run with gpt-4o-mini (default in config)
RUN_ID="thesis_$(date +%Y%m%d_%H%M%S)"
fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"

# Evaluate
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

# Check for errors
python -c "import json; d=json.load(open('runs/${RUN_ID}/meeting_output.json')); print('Parse errors:', len(d.get('json_parse_errors',[])), 'Incomplete:', len(d.get('incomplete_reviewers',[])))"
```

**Note for zsh users**: Avoid pasting commands with `#` comments in interactive shell.
Use the `./run_example.sh` script instead.

---

## Model Selection

### gpt-4o-mini (Default, Recommended)

- Full support for temperature, top_p, sampling parameters
- Reliable JSON output with `response_format`
- Cost-effective for thesis experiments

### Newer GPT Models

Some newer models have API restrictions:
- Only support `temperature=1` (default) - custom values are ignored with warning
- Do not support `top_p`, `presence_penalty`, `frequency_penalty`
- Use `max_completion_tokens` instead of `max_tokens` (handled automatically)

The provider handles these automatically - logs a warning and continues.

### Structured JSON Output

Reviewer and Scribe agents use strict JSON Schema output:
- Schema validation ensures all required fields are present
- Empty/truncated responses trigger automatic retry (up to 1x with 2x token limit)
- Failed outputs are marked as `is_incomplete: true` in `reviewer_outputs.json`

If you see `incomplete_reviewers` in meeting_output.json:
1. Check `runs/<run_id>/debug/` for raw response files
2. Consider increasing `max_tokens` in config
3. Check network connectivity or API rate limits

### Manual Run (Legacy)

```bash
# Set your API key
export OPENAI_API_KEY="sk-..."

# Run with gpt-4o-mini (default in configs)
fagan run --config configs/examples/c1_ubr.yaml --run-id my_run

# Evaluate
fagan eval --run my_run --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

### Using Older Models (GPT-4)

To use GPT-4 models, update the config:

```yaml
llm_params:
  provider: "openai"
  model: "gpt-4o-mini"  # Uses legacy max_tokens parameter
  temperature: 0.2
  max_tokens: 4096
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| API key error | Set `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY` for Claude) |
| max_tokens error | Some models use max_completion_tokens (handled automatically) |
| temperature error | Some models don't support custom temperature (auto-ignored with warning) |
| Artifact not found | Check path in config, ensure file exists |
| Leakage guard error | Don't load files from `artifacts/gold/` |
| Import error | Run `pip install -e .` |
| Tests fail | Check Python version (3.11+ required) |
| JSON parse errors | Check `runs/<run_id>/debug/` for raw LLM responses |

## Debugging JSON Parse Failures

When the LLM returns invalid JSON, debug files are saved automatically:

```bash
# Location of debug files
ls runs/<run_id>/debug/

# View a raw response that failed to parse
cat runs/<run_id>/debug/raw_response_reviewer_*.txt
```

JSON parse errors are also recorded in `meeting_output.json`:
```bash
cat runs/<run_id>/meeting_output.json | jq '.json_parse_errors'
```

The system uses OpenAI's `response_format: {type: "json_object"}` to enforce
structured JSON output, significantly reducing parse failures.

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_matcher.py

# With coverage
pytest --cov=src/fagan_tool tests/
```

## Development

### Add Reading Technique
1. Edit `src/fagan_tool/core/schemas.py` (add enum)
2. Create `prompts/reviewer_<technique>.txt`
3. Update `ReviewerAgent._get_prompt_file()`

### Add LLM Provider
1. Create `src/fagan_tool/providers/<name>_provider.py`
2. Inherit from `LLMProvider`
3. Register in `factory.py`

### Modify Prompts
Edit files in `prompts/` directory - changes take effect immediately.

## Important Rules

1. **NEVER** place gold standard in `artifacts/input/`
2. **ALWAYS** snapshot configs for reproducibility
3. **USE** dry-run for testing before API calls
4. **VERSION** your prompts in config
5. **TRACK** prompt changes for experiments

## Help

```bash
# General help
fagan --help

# Command help
fagan run --help
fagan eval --help
fagan report --help
```

## Documentation

- `README.md` - Full documentation
- `ARCHITECTURE.md` - Technical details
- `USAGE_EXAMPLES.md` - Detailed examples
- `PROJECT_STRUCTURE.md` - File organization

## Contact

For issues, see README.md or open a GitHub issue.
