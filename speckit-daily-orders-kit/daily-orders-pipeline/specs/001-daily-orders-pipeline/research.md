# Research: Daily Orders Pipeline

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-30

Technical Context had no open NEEDS CLARIFICATION items. The user fixed the stack (Python 3.11+,
DuckDB, pytest, `src/` package, CLI flags, Parquet + DuckDB + `run_report.json`). This file
records the design decisions made inside that stack.

## R1. How CSV files are read

- **Decision**: Python's standard-library `csv` module reads each file and checks its header. It
  records the physical line number and field count of every record and keeps every value as the
  original string. The rows are bulk-inserted into a DuckDB table `raw_rows` in which every column
  is VARCHAR. All work after that is done in SQL.
- **Rationale**: the spec needs, for every rejected row, the line number, the original values
  exactly as received (FR-019), and detection of rows with the wrong number of fields (FR-011).
  With the `csv` module each of these is one line of code and fully deterministic. Once the data
  is in `raw_rows`, validation, de-duplication, revisions and the summary are all SQL, which
  satisfies Principle VII (SQL for transformations; Python for file discovery and I/O).
- **Alternatives considered**:
  - DuckDB `read_csv(..., all_varchar=true, store_rejects=true)`: this is pure SQL, but malformed
    rows go to a separate rejects table with a different shape. Line numbers for good rows would
    also rely on insertion order, which is harder to guarantee. Rejected as more fragile for a
    small gain.
  - pandas: not needed. The user asked for pandas only if unavoidable.

## R2. Where validation happens and how reason codes are chosen

- **Decision**: one SQL step builds `std_rows` from `raw_rows`. It trims every value and
  lower-cases `category` and `status` (FR-004). A single `CASE` expression then assigns
  `reject_reason`, with its branches in the FR-012 precedence order. The first branch that matches
  wins, so each row gets exactly one code.
  - `order_date`: must match `^\d{4}-\d{2}-\d{2}$` **and** `TRY_CAST(... AS DATE)` must succeed.
    The regex check comes first, so DuckDB's permissive casting cannot accept other formats.
  - `quantity`: must match `^[0-9]+$` and have a value of 1 or more.
  - `unit_price`: must match `^[0-9]+(\.[0-9]{1,2})?$` and be greater than 0. Stored as
    `DECIMAL(12,2)`. The regex rejects `-9.99`, `1e3`, `.5` and thousands separators.
  - `future_order_date`: `order_date > business_date`, where `business_date` comes from the file
    name. The check never reads the system clock (constitution V, spec FR-007).
- **Rationale**: a `CASE` expression with branches in order is the simplest deterministic way to
  implement FR-012. Checking the format with a regex before casting prevents the cast from
  accepting values the spec says to reject.
- **Alternatives considered**: recording every failing code per row. The spec requires a single
  code (FR-012), and a single code keeps the per-reason counts adding up to `rows_rejected`.

## R3. Order of de-duplication, conflicts and revisions

Only rows that pass validation (`reject_reason IS NULL`) take part. The steps run in this order,
and each is a SQL step:

1. **Exact duplicates (FR-014)**: rows are grouped by the 8 standardised columns. Within each
   group, one representative row is kept, picked by ordering on `business_date ASC,
   revision DESC, source_file ASC, line_number ASC`. The other rows are marked `superseded` with
   `superseded_reason = 'exact_duplicate'`.
   - This ordering agrees with the rules for revisions (highest revision wins) and for
     cross-date conflicts (earliest business date wins).
2. **Same order_id within one file (FR-017)**: among the representatives, if an `order_id`
   appears more than once in the same `source_file`, every such row is rejected with
   `conflicting_order_id`. This runs before step 3, so a clash inside one file is never settled
   by a revision.
3. **Revisions (FR-015, FR-016)**: for each `(business_date, order_id)`, the row with the
   highest `revision` is kept. The others are marked `superseded` with
   `superseded_reason = 'older_revision'`. An order that appears only in a lower revision is
   kept, because it has nothing to compete with.
4. **Order_id on different business dates (FR-017a)**: for each `order_id`, the row with the
   lowest `business_date` is kept. The others are rejected with `conflicting_order_id`.

- **Rationale**: each step is one window-function query (`ROW_NUMBER` or `COUNT(*) OVER`). Every
  row that goes into a step comes out of it either still valid, `superseded` or `rejected`, so no
  row can be lost between steps.
- **Invalid correction** (spec edge case): step R2 has already rejected the invalid r2 row, so the
  r1 row never meets it in step 3 and stays clean.
- **Expected result on the sample data**:
  - 138 rows read.
  - 9 rejected.
  - 5 superseded: 3 exact duplicates and 2 older revisions.
  - 124 clean.
  - Reject rate 9 / 138 = 6.52%, so the gate passes.

## R4. Row lineage and reconciliation

- **Decision**: every raw row gets a stable `row_id` = `source_file || ':' || line_number`. The
  pipeline builds a table `row_outcomes(row_id, outcome, reason)`, where `outcome` is one of
  `clean`, `rejected` or `superseded`. Reconciliation (FR-023) runs three checks:
  - `COUNT(raw_rows) = COUNT(row_outcomes)`;
  - `row_id` is unique in `row_outcomes`;
  - the per-outcome counts equal the row counts of `clean_orders` and `rejected_orders`, and the
    superseded count.
- **Rationale**: this proves "each row lands in exactly one place" (constitution II) row by row,
  not only through totals.

## R5. Quality gate and failed runs

- **Decision**:
  - `reject_rate = rows_rejected / rows_read`, which is 0 when `rows_read = 0`.
  - The run fails when `reject_rate > max_reject_rate`, compared as exact decimals, so exactly
    0.10 passes.
  - On failure, nothing in the output folder is replaced except `run_report.json` (gate
    `failed`) and `pipeline.log`.
  - A failed run's quarantine rows are not published, because publishing them would leave
    `rejected_orders` out of step with the previous run's `clean_orders`. The per-reason counts in
    the report are enough to diagnose the problem.
- **Rationale**: this follows FR-024 and constitution IV. Earlier successful outputs are never
  partially overwritten.
- **Alternatives considered**: writing the failed quarantine to a side folder. Rejected for now
  as extra surface that no requirement asks for (Principle VII).

## R6. Atomic, idempotent publishing

- **Decision**: all outputs are written first into `<output>/.staging/`, which is deleted and
  recreated at the start of each run. Each Parquet file is written with
  `COPY (SELECT ... ORDER BY <documented key>) TO ... (FORMAT parquet)`. The DuckDB file is built
  in staging with `CREATE TABLE ... AS SELECT ... ORDER BY`. Only after the gate and
  reconciliation pass is each file moved into place with `os.replace`.
- **Rationale**: every run fully replaces its outputs (FR-022), and nothing depends on state
  from an earlier run (Principle I). Rebuilding from scratch keeps it simple, and the data volume
  is tiny.
- **Determinism**:
  - Outputs are compared by content: same rows, values and order. They are not compared byte for
    byte, because DuckDB file internals are not guaranteed to be byte-stable.
  - `run_report.json` contains no timestamps or absolute paths, and its keys and lists are
    sorted, so it is byte-identical across runs on the same input.
  - `pipeline.log` may contain timestamps. It is diagnostic only and not a data output.

## R7. Revenue arithmetic

- **Decision**:
  - `line_revenue = quantity * unit_price`, stored as `DECIMAL(18,2)`.
  - The summary's `revenue` is `SUM(line_revenue)` over completed orders only (spec Q1), also
    `DECIMAL(18,2)`.
  - `orders = COUNT(*)` and `units = SUM(quantity)`.
- **Rationale**: exact decimal arithmetic avoids floating-point drift that would make totals
  differ by fractions of a cent.

## R8. Packaging and running

- **Decision**:
  - `pyproject.toml` with a src layout: package `orders_pipeline`, requiring `python >= 3.11`
    and `duckdb >= 1.1`.
  - Optional dev dependencies: `pytest`.
  - Installed with `uv pip install -e ".[dev]"`, or `pip install -e ".[dev]"`.
  - The entry point is `python -m orders_pipeline` via `__main__.py`, with argument parsing by
    the standard-library `argparse`.
- **Rationale**: minimal dependencies, and it matches the user's command line exactly.

## R9. Test strategy

- **Decision**:
  - pytest tests are written before the implementation (constitution V).
  - Two kinds of tests:
    - **Rule tests** build tiny CSV fixtures in `tmp_path`, one business rule per test.
    - **Sample-data tests** run the full CLI on a copy of the 4 provided files, committed under
      `data/incoming/`, and assert the exact expected counts from R3.
  - No network, clock or randomness. The idempotency test runs the pipeline twice and compares
    every output table and the report.
- **Rationale**: the rule tests pin down the spec's requirements, and the sample-data tests prove
  the success criteria (SC-001 to SC-004, SC-006).
