# Starter Constitution: Data Pipeline Principles (DRAFT - edit me)

This is a starting draft for the Daily Orders exercise (Course Sitting 3,
Step A). Edit it, then paste it into your `/speckit-constitution` prompt.
Lines marked **[YOUR CALL]** are decisions your team has to make. Do not
leave them blank.

## Core Principles

### I. Idempotent and Re-runnable (NON-NEGOTIABLE)
Running a pipeline twice on the same inputs MUST produce identical outputs.
A re-run never creates duplicates and never depends on hidden state from an
earlier run.

### II. No Silent Data Loss
Every input row MUST end up in exactly one place: the clean output, the
rejected (quarantine) output, or explicitly counted as a superseded
duplicate. Row counts MUST be reconciled at the end of every run, and any
mismatch fails the run.

### III. Validate at the Boundary
Inputs are validated as they enter the pipeline (file name, columns, types,
ranges, formats). Invalid rows are quarantined with a machine-readable
reject reason. They are never silently dropped and never "fixed" by
guessing.

### IV. Data-Quality Gates
A run FAILS, and publishes no clean output, when the share of rejected rows
exceeds a configurable threshold.
Default threshold: 10%

### V. Test-First
Business rules are covered by automated tests written before the code they
exercise. Tests run against the provided sample data and are deterministic
(no network, no clock, no randomness).

### VI. Configuration, Not Hardcoding
Paths, thresholds and environment-specific values come from CLI arguments
or config files. No secrets, credentials or absolute paths in the
repository.

### VII. Keep It Simple
Prefer plain SQL (DuckDB) over custom code. Do not add frameworks,
orchestrators or abstractions until a written requirement needs them.

### VIII. Observable Runs
Every run writes a run report (files read, rows read/rejected/kept, reject
reasons, gate status). Logs are plain text, one line per event.

## Technology Constraints
- Python 3.11+, DuckDB, pytest. Runs locally with no cloud services.
- Outputs: Parquet files plus a DuckDB database file.
- Late-arriving data rule:
  **[YOUR CALL: how are late or corrected files treated?]**
- Dates and time zones:
  **[YOUR CALL: e.g. ISO-8601 calendar dates, no time zones]**

## Naming and Layout
- Tables and columns: `snake_case`. Output tables: `clean_<entity>`,
  `rejected_<entity>`, `<grain>_<metric>_summary`.
- Input file naming is part of the contract. Unexpected file names fail the
  run.

## Governance
- This constitution overrides personal preference. A plan that violates it
  must justify the exception in writing.
- Changes to this file go through a merge request and are reviewed like
  code.

**Version**: 0.1 (draft)
