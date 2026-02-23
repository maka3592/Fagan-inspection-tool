# Fagan Inspection Tool

Multi-agent LLM-based formal software inspection tool implementing Michael Fagan's methodology.

## Quick Reference

```bash
# Run tests
pytest tests/

# Dry run (no API key needed)
fagan dry-run

# Run inspection
fagan run --config configs/examples/c1_ubr.yaml

# Evaluate against gold standard
fagan eval --run <run_id> --gold artifacts/gold/Faults_List_In_ver6.xls
```

## Project Structure

- `src/fagan_tool/` - Main source code
  - `core/` - Schemas and process orchestration
  - `agents/` - Moderator, Reviewer, Scribe agents
  - `providers/` - LLM provider abstraction (OpenAI, Anthropic)
  - `evaluation/` - Matching and metrics
  - `utils/` - PDF extraction, leakage guard, artifact loading
  - `cli.py` - Command-line interface
- `prompts/` - Versioned agent prompt templates
- `configs/` - Inspection configurations and checklists
- `artifacts/input/` - Input documents (design, usecases, guides)
- `artifacts/gold/` - Gold standard (evaluation only, NEVER load into agents)
- `runs/` - Inspection run outputs
- `eval/` - Evaluation results
- `tests/` - Unit tests

## Critical Rules

1. **NEVER access `artifacts/gold/`** from agent code - LeakageGuard enforces this
2. Run IDs auto-increment if directory exists (prevents overwriting)
3. Incomplete defects (missing required fields) go to `meeting_output.json`, not `final_defects.json`

## Reading Techniques

- **UBR** (Usage-Based Reading) - Design/MSC focus
- **CBR** (Checklist-Based Reading) - Systematic checklist
- **PBR** (Perspective-Based Reading) - Tester/Designer/User perspectives

## Environment Variables

```bash
export OPENAI_API_KEY="..."      # Default provider
export ANTHROPIC_API_KEY="..."   # Optional
```
