# Architecture Documentation

## System Overview

The Fagan Inspection Tool implements a multi-agent architecture for formal software inspection, following the Fagan process methodology.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│                    (typer + rich)                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                   Process Orchestration                      │
│                    (FaganProcess)                            │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┐   │
│  │Planning│Kick-Off│ Prep   │Inspect │Meeting │Follow  │   │
│  │        │        │        │        │        │Up      │   │
│  └────────┴────────┴────────┴────────┴────────┴────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
┌─────────▼──────┐ ┌──▼─────────┐ ┌▼──────────┐
│  Moderator     │ │  Reviewer  │ │  Scribe   │
│  Agent         │ │  Agents    │ │  Agent    │
└────────┬───────┘ └──┬─────────┘ └┬──────────┘
         │            │             │
         └────────────┼─────────────┘
                      │
          ┌───────────▼───────────┐
          │   LLM Provider        │
          │   (OpenAI/Anthropic)  │
          └───────────────────────┘
```

## Core Modules

### 1. Core Package (`src/fagan_tool/core/`)

#### schemas.py
- Pydantic models for all data structures
- Type-safe configuration and results
- Validation and serialization

Key models:
- `Defect`: Individual defect finding
- `ReviewerOutput`: Results from single reviewer
- `MeetingOutput`: Consolidated results
- `InspectionConfig`: Run configuration
- `InspectionRun`: Complete run data
- `EvaluationMetrics`: Performance metrics

#### process.py
- Main orchestration logic
- Implements all 7 Fagan phases
- Manages agent lifecycle
- Handles artifact loading and result saving

### 2. Agents Package (`src/fagan_tool/agents/`)

#### base_agent.py
- Abstract base class for all agents
- Common functionality: prompt loading, LLM calling, JSON parsing
- Shared utilities

#### reviewer_agent.py
- Performs individual inspection
- Technique-specific prompting
- Defect extraction and structuring

Key methods:
- `inspect()`: Main inspection logic
- `_format_artifacts()`: Prepares artifact context
- `_get_prompt_file()`: Maps technique to prompt

#### scribe_agent.py
- Consolidates reviewer findings
- Duplicate detection
- Conflict resolution
- Meeting minutes generation

Key methods:
- `consolidate()`: Main consolidation logic
- `_format_reviewer_outputs()`: Prepares meeting context

#### moderator_agent.py
- Planning phase
- Kick-off coordination
- Follow-up quality checks

Key methods:
- `plan_inspection()`: Entry criteria and scope
- `conduct_kickoff()`: Role assignment
- `follow_up()`: Quality validation

### 3. Providers Package (`src/fagan_tool/providers/`)

#### base.py
- Abstract LLM provider interface
- Model-agnostic design

#### anthropic_provider.py
- Anthropic Claude integration
- Message formatting
- API call handling

#### openai_provider.py
- OpenAI integration
- Compatible API format

#### factory.py
- Provider instantiation
- Configuration parsing

### 4. Utils Package (`src/fagan_tool/utils/`)

#### pdf_extractor.py
- PDF text extraction with page tracking
- Section detection heuristics
- Text chunking for LLM context

Key features:
- Page-by-page extraction
- Heading detection
- Context windowing

#### artifact_loader.py
- Artifact loading and management
- Metadata extraction
- **Leakage protection integration**

Key features:
- Multi-format support (PDF, text)
- Automatic type inference
- Safe loading with validation

#### leakage_guard.py
- **Critical security component**
- Prevents gold standard contamination
- Path validation

Protection mechanisms:
- Forbidden path patterns
- Filename validation
- Multi-path batch validation

### 5. Evaluation Package (`src/fagan_tool/evaluation/`)

#### gold_loader.py
- Excel parsing
- Gold standard normalization
- Flexible column mapping

#### matcher.py
- Defect matching algorithm
- Fuzzy string matching (rapidfuzz)
- Duplicate detection

Matching strategy:
1. Position similarity (30% weight)
2. Description similarity (60% weight)
3. Risk/Type match bonus (10% weight)

Match types:
- EXACT: High similarity (>85%)
- PARTIAL: Medium similarity (60-85%)
- DUPLICATE: Multiple findings of same defect
- NO_MATCH_POTENTIAL_NEW: Unmatched, high confidence
- NO_MATCH_FALSE_POSITIVE: Unmatched, low confidence

#### metrics.py
- Precision/Recall calculation
- Risk-level breakdown
- Statistical analysis

## Data Flow

### Inspection Run Flow

```
1. Configuration Loading
   ├─ YAML/JSON → InspectionConfig
   └─ Validation

2. Artifact Loading
   ├─ Path validation (LeakageGuard)
   ├─ PDF extraction
   └─ Metadata generation

3. Planning Phase
   ├─ Moderator analyzes artifacts
   ├─ Entry criteria check
   └─ Scope definition

4. Individual Inspection
   ├─ For each technique:
   │  ├─ Create ReviewerAgent
   │  ├─ Load technique prompt
   │  ├─ Format artifact context
   │  ├─ Call LLM
   │  └─ Parse defects
   └─ Collect ReviewerOutputs

5. Inspection Meeting
   ├─ ScribeAgent receives all outputs
   ├─ Consolidation logic:
   │  ├─ Duplicate detection
   │  ├─ Conflict resolution
   │  └─ Evidence merging
   ├─ Generate minutes
   └─ Exit decision

6. Follow-Up
   ├─ Moderator quality check
   ├─ Evidence validation
   └─ Approval/rejection

7. Result Persistence
   ├─ JSON serialization
   └─ File output
```

### Evaluation Flow

```
1. Run Results Loading
   └─ final_defects.json

2. Gold Standard Loading
   ├─ Excel parsing
   └─ Normalization

3. Matching Process
   ├─ Position similarity
   ├─ Description similarity
   ├─ Duplicate detection
   └─ Classification

4. Metrics Calculation
   ├─ TP/FP/FN counting
   ├─ Precision/Recall
   └─ Risk breakdown

5. Report Generation
   └─ Markdown output
```

## Key Design Patterns

### 1. Agent Pattern
- Each role is an agent with specific capabilities
- Agents communicate through structured data (Pydantic models)
- Loose coupling via provider abstraction

### 2. Strategy Pattern
- Reading techniques are strategies
- Swappable prompt templates
- Uniform interface

### 3. Template Method Pattern
- BaseAgent defines common flow
- Subclasses implement specifics
- Consistent structure

### 4. Factory Pattern
- Provider creation
- Configuration-driven instantiation

### 5. Guard Pattern
- LeakageGuard protects data integrity
- Fail-fast on violations
- No silent failures

## Extensibility Points

### Adding New Reading Techniques

1. Define enum in `schemas.py`:
```python
class ReadingTechnique(str, Enum):
    MY_TECHNIQUE = "MY_TECHNIQUE"
```

2. Create prompt template:
```
prompts/reviewer_my_technique.txt
```

3. Update `ReviewerAgent._get_prompt_file()`:
```python
technique_map = {
    ReadingTechnique.MY_TECHNIQUE: "reviewer_my_technique.txt",
    # ...
}
```

### Adding New LLM Providers

1. Create provider class:
```python
class MyProvider(LLMProvider):
    def generate(self, messages, system=None):
        # Implementation
        pass

    def get_provider_name(self):
        return "my_provider"
```

2. Register in factory:
```python
provider_map = {
    "my_provider": MyProvider,
    # ...
}
```

### Adding New Evaluation Metrics

Extend `MetricsCalculator`:
```python
@staticmethod
def calculate_custom_metric(found_defects, gold_defects):
    # Implementation
    pass
```

## Testing Strategy

### Unit Tests
- `test_schemas.py`: Data model validation
- `test_leakage_guard.py`: Security testing
- `test_matcher.py`: Matching algorithm

### Integration Tests
- Dry-run mode for end-to-end testing
- No API calls required
- Deterministic outputs

### Manual Testing
- Example configurations
- Documentation with expected outputs

## Performance Considerations

### LLM API Calls
- Batch reviewer calls in parallel (not yet implemented)
- Use appropriate max_tokens
- Consider rate limits

### PDF Processing
- Lazy loading
- Chunking for large documents
- Page-level caching possible

### Matching Performance
- O(n*m) complexity for n found, m gold
- Rapidfuzz is optimized
- Could be parallelized for large datasets

## Security and Data Integrity

### Leakage Prevention
- **Critical for research validity**
- Multiple layers of protection
- Explicit validation at load time

### API Key Management
- Environment variables only
- Never committed to code
- `.gitignore` configured

### Data Separation
- Input artifacts: `artifacts/input/`
- Gold standard: `artifacts/gold/`
- Never mixed in agent context

## Future Enhancements

### Potential Improvements
1. Parallel reviewer execution
2. Streaming LLM responses
3. Interactive meeting simulation
4. Advanced duplicate detection (embeddings)
5. Cost tracking per run
6. Web UI for result visualization
7. Multi-language support
8. Rework phase automation (code patching)

### Scalability
- Currently designed for single-document inspections
- Could be extended to:
  - Multi-document projects
  - Continuous inspection (CI/CD integration)
  - Large-scale batch processing

## Dependencies

### Critical Dependencies
- **typer**: CLI framework
- **pydantic**: Data validation
- **anthropic**: Claude API client
- **openai**: OpenAI API client
- **pdfplumber**: PDF extraction
- **rapidfuzz**: Fuzzy matching
- **rich**: Terminal formatting

### Development Dependencies
- **pytest**: Testing framework
- **black**: Code formatting
- **ruff**: Linting

## Version History

- **v0.1.0**: Initial implementation
  - Complete Fagan process
  - UBR/CBR/PBR techniques
  - OpenAI/Anthropic support
  - Evaluation framework
