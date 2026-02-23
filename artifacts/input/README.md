# Input Artifacts Directory

Place your inspection artifacts in the appropriate subdirectories:

## Directory Structure

- **design/**: Design documents (e.g., STLDD PDFs like `Taxi_des_exp_v2.pdf`)
- **usecases/**: Use case specifications (e.g., `UseCasesRank_v3.4.pdf`)
- **requirements/**: Requirements documents (e.g., `TextReqSpec_v3.6.pdf`)
- **guides/**: Reading technique guides (e.g., `GuideUBR_rankbased_v2.pdf`)

## Supported Formats

- PDF files (`.pdf`) - Recommended
- Plain text files (`.txt`)

## Important: Leakage Protection

**NEVER place gold standard files in this directory!**

Gold standard files must be kept in `artifacts/gold/` and will never be loaded into agent context. This ensures evaluation integrity.

## Example Files

For your research project, typical files might include:

```
artifacts/input/
├── design/
│   └── Taxi_des_exp_v2.pdf           # STLDD design document
├── usecases/
│   └── UseCasesRank_v3.4.pdf         # Use case specifications
├── requirements/
│   └── TextReqSpec_v3.6.pdf          # Textual requirements
└── guides/
    └── GuideUBR_rankbased_v2.pdf     # UBR technique guide
```

## Referencing in Configs

In your inspection configuration files, reference these artifacts using relative paths:

```yaml
artifacts:
  - "design/Taxi_des_exp_v2.pdf"
  - "usecases/UseCasesRank_v3.4.pdf"
  - "guides/GuideUBR_rankbased_v2.pdf"
```

## Quick Check

Before running an inspection, verify your artifacts are in place:

```bash
ls -R artifacts/input/
```
