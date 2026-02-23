# Gold Standard Directory

This directory contains the **ground truth** defect lists used for evaluation.

## Important: Strict Separation

**CRITICAL: Gold standard files in this directory must NEVER be loaded into agent context!**

The tool includes built-in **LeakageGuard** protection to prevent accidental contamination:

- Any attempt to load files from `artifacts/gold/` into agent prompts will raise an exception
- Gold data is ONLY used by the evaluation module
- This ensures scientific integrity and prevents data leakage

## Expected Files

Place your gold standard file here:

```
artifacts/gold/
└── Faults_List_In_ver6.xls    # or .xlsx
```

## Gold Standard Format

The gold standard Excel file should contain columns such as:

- **ID**: Defect identifier
- **Position** or **Section**: Location in document
- **Risk** or **Severity**: A/B/C classification
- **Type** or **FaultType**: M (Missing) or W (Wrong)
- **Description**: Defect description
- **Page**: Page number (optional)

The tool's `GoldLoader` will attempt to match common column name variations.

## Usage

Gold standard files are referenced in evaluation commands:

```bash
fagan eval --run c1_ubr_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
```

## Security Note

If your gold standard contains sensitive information:

1. Add it to `.gitignore` (already configured)
2. Never commit it to version control
3. Store it securely and separately from the repository

## Verification

To verify the leakage guard is working:

```python
from fagan_tool.utils.leakage_guard import LeakageGuard

# This should raise ValueError
LeakageGuard.validate_path("artifacts/gold/Faults_List_In_ver6.xls")
```

## Column Name Mapping

The `GoldLoader` supports various column names:

| Expected | Alternatives |
|----------|--------------|
| ID | Defect_ID, DefectID |
| Position | Section, Location |
| Risk | Severity, Priority |
| Type | FaultType, Fault_Type |
| Description | Summary, Details |
| Page | PageNum, Page_Number |

If your gold standard uses different column names, you may need to adjust `gold_loader.py`.
