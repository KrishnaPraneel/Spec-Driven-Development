# Implementation Plan: Daily Orders Pipeline

**Branch**: `001-daily-orders-pipeline` | **Date**: 2026-09-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-daily-orders-pipeline/spec.md`

## Summary

The pipeline is a local batch CLI, `python -m orders_pipeline`. It reads every
`orders_<date>_r<N>.csv` file in an input folder and produces:
- a one-row-per-order `clean_orders` table;
- a `rejected_orders` quarantine table with one reason code per row;
- a completed-orders-only `daily_sales_summary` by order date and category;

plus a deterministic `run_report.json`. The first two tables and the summary are published as
Parquet files and in one DuckDB database file.

Python (standard-library `csv`) only discovers the files, checks their contract, and loads raw
string values into DuckDB. Everything else is ordered SQL steps: standardise, validate, collapse
exact duplicates, handle in-file conflicts, resolve revisions, handle cross-date conflicts,
build the outputs, and reconcile. Outputs are built in a staging folder and moved into place
only if the 10% reject gate and every reconciliation invariant pass.

## Technical Context

**Language/Version**: Python 3.11+ (3.12 available locally)

**Primary Dependencies**: `duckdb` (>= 1.1). Standard library: `csv`, `argparse`, `json`,
`logging`, `pathlib`. No pandas.

**Storage**: Output folder with 3 Parquet files, `orders.duckdb`, `run_report.json` and
`pipeline.log`. Processing uses an in-memory DuckDB connection.

**Testing**: pytest. Tests are written before the implementation; the fixtures are tiny CSVs in
`tmp_path` plus the 4 committed sample files.

**Target Platform**: A local developer machine (macOS/Linux). No cloud and no network.

**Project Type**: A single-package CLI tool.

**Performance Goals**: A day's files of a few thousand rows processed in under 1 minute (SC-007).
In practice the expected time is a few seconds.

**Constraints**:
- Deterministic outputs.
- No reads of the system clock in business logic.
- No absolute paths or secrets in the repository.
- Outputs published atomically.

**Scale/Scope**: Tens of files and at most tens of thousands of rows per run. Each run does a
full rebuild with no incremental state.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How the plan complies | Pre-design | Post-design |
|---|---|---|---|
| I. Idempotent (NON-NEGOTIABLE) | Full rebuild from inputs each run. Every output uses `ORDER BY`. Staging is recreated each run and outputs are replaced whole. The report has no timestamps. The idempotency test runs the pipeline twice and compares (R6). | ✅ | ✅ |
| II. No silent data loss | `row_outcomes` gives each `row_id` exactly one outcome. Five invariants are checked, and a failure means exit 1 (data-model.md). | ✅ | ✅ |
| III. Validate at boundary | File-name and header checks run before any data is read. Row rules use a fixed-precedence `CASE`. Raw values are kept in quarantine. Only trimming and lower-casing are allowed; nothing is guessed (R2). | ✅ | ✅ |
| IV. Data-quality gate | `--max-reject-rate`, default 0.10, compared strictly (`>`) with exact decimals. On failure nothing is published and the report is still written (R5). | ✅ | ✅ |
| V. Test-first | The tasks put tests before code. Tests use no network, clock or randomness. Future dates are judged against the business date in the file name, not today (R9). | ✅ | ✅ |
| VI. Configuration | All paths and the threshold come from CLI flags. No absolute paths, and the report stores base file names only. | ✅ | ✅ |
| VII. Keep it simple | One package, a few modules, and SQL files for the logic. No pandas, no framework, no orchestrator. Python reads the CSVs; see R1 for why this falls within "file discovery and I/O". | ✅ | ✅ |
| VIII. Observable runs | Every run writes `run_report.json`, including failed runs. The log is plain text with one line per event (contracts/). | ✅ | ✅ |
| Tech constraints: latest revision wins | For each `(business_date, order_id)` the highest `r<N>` from the file name wins. Rows only in earlier revisions are kept (R3 step 3). | ✅ | ✅ |
| Tech constraints: dates | Strict `YYYY-MM-DD` regex plus a cast to `DATE`. No times or time zones (R2). | ✅ | ✅ |
| Naming | `clean_orders`, `rejected_orders` and `daily_sales_summary` follow `<grain>_<metric>_summary`; all columns are snake_case. | ✅ | ✅ |

**Result**: PASS. There are no violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-daily-orders-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions R1–R9
├── data-model.md        # Phase 1: tables, rules, invariants
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli.md           # Flags, input contract, exit codes, output layout, log format
│   └── run-report.md    # run_report.json shape and rules
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
pyproject.toml                    # package metadata; deps: duckdb; dev: pytest
data/
└── incoming/                     # the 4 sample CSVs (test and quickstart input)
src/
└── orders_pipeline/
    ├── __init__.py
    ├── __main__.py               # python -m orders_pipeline → cli.main()
    ├── cli.py                    # argparse, exit codes, logging setup
    ├── ingest.py                 # file discovery, name/header contract, csv → raw_rows
    ├── transform.py              # runs sql/*.sql in order on one DuckDB connection
    ├── publish.py                # gate, reconciliation, staging → atomic replace
    ├── report.py                 # builds run_report.json deterministically
    └── sql/
        ├── 10_standardise_validate.sql
        ├── 20_exact_duplicates.sql
        ├── 30_in_file_conflicts.sql
        ├── 40_revisions.sql
        ├── 50_cross_date_conflicts.sql
        ├── 55_row_outcomes.sql
        ├── 60_clean_orders.sql
        ├── 61_rejected_orders.sql
        ├── 62_daily_sales_summary.sql
        └── 70_reconcile.sql      # invariant checks → one row of booleans
tests/
├── conftest.py                   # helpers: write CSV fixtures, run the CLI in-process
├── test_file_contract.py         # FR-001, FR-002, empty folder, exit code 2
├── test_validation.py            # FR-004–FR-013: one test per reason code and precedence
├── test_dedup_revisions.py       # FR-014–FR-017a
├── test_summary.py               # FR-020, completed-only, decimal revenue
├── test_gate_reconciliation.py   # FR-023, FR-024, exactly-10% boundary, earlier outputs untouched
├── test_idempotency.py           # FR-022, FR-027, file-order independence
├── test_quarantine.py            # FR-019: raw values, line numbers, malformed rows
├── test_run_report.py            # run-report contract and log format (FR-025, FR-026)
└── test_sample_data.py           # end-to-end on data/incoming: 138/124/9/5 counts, SC-001–SC-004
```

`output/` is git-ignored.

**Structure Decision**: a single project using a src layout with one package. The business logic
is in numbered SQL files so that each rule can be reviewed as SQL. The Python modules only
contain I/O and orchestration.

## Complexity Tracking

No constitution violations. Nothing to justify.
