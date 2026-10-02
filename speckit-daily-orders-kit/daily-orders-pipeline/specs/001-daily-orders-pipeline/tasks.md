---

description: "Task list for the Daily Orders Pipeline"
---

# Tasks: Daily Orders Pipeline

**Input**: Design documents from `/specs/001-daily-orders-pipeline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md,
contracts/run-report.md, quickstart.md

**Tests**: REQUIRED. Constitution Principle V and the plan require tests to be written first.
Every test task comes before its implementation task and MUST be run and seen to FAIL before the
implementation is written. Tests must not use the network, the clock or randomness.

**Organization**: tasks are grouped by user story (US1–US4 from spec.md) so that each story can
be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story the task belongs to (US1, US2, US3, US4)
- All paths are relative to the project root `daily-orders-pipeline/`

## Reference facts (used by several tasks)

**Expected header**, in this exact order:
`order_id,customer_id,order_date,product_id,category,quantity,unit_price,status`

**File name regex**: `^orders_(\d{4}-\d{2}-\d{2})_r([1-9][0-9]*)\.csv$`

**Reject reason precedence** (FR-012). A row gets the first code that applies:

1. `malformed_row`: `field_count <> 8`
2. `missing_order_id`: trimmed `order_id` is blank
3. `missing_customer_id`: trimmed `customer_id` is blank
4. `missing_product_id`: trimmed `product_id` is blank
5. `invalid_order_date`: "does not match `^\d{4}-\d{2}-\d{2}$`, or is not a real date"
6. `future_order_date`: "`order_date > business_date`"
7. `invalid_quantity`: "does not match `^[0-9]+$`, or is less than 1"
8. `invalid_unit_price`: "does not match `^[0-9]+(\.[0-9]{1,2})?$`, or is 0 or less"
9. `invalid_category`: "not in {`electronics`, `home`, `grocery`, `apparel`}"
10. `invalid_status`: "not in {`completed`, `cancelled`}"
11. `conflicting_order_id`: assigned by the in-file and cross-date conflict steps

**Sample data expectations** (the 4 files in `data/incoming/`):

- **Counts**: 138 rows read, 124 clean, 9 rejected, 5 superseded (`exact_duplicate` 3,
  `older_revision` 2). Reject rate `0.0652`, so the gate passes.
- **The 9 rejected rows**, as `source_file:line_number` → reason:
  - `orders_2026-09-01_r1.csv:14` → `invalid_quantity` (ORD-000013)
  - `orders_2026-09-01_r1.csv:22` → `invalid_order_date` (ORD-000021)
  - `orders_2026-09-02_r1.csv:7` → `missing_customer_id` (ORD-000106)
  - `orders_2026-09-02_r1.csv:12` → `invalid_quantity` (ORD-000111)
  - `orders_2026-09-02_r1.csv:17` → `invalid_unit_price` (ORD-000116)
  - `orders_2026-09-02_r1.csv:22` → `invalid_order_date` (ORD-000121)
  - `orders_2026-09-02_r1.csv:27` → `missing_order_id`
  - `orders_2026-09-03_r1.csv:10` → `future_order_date` (ORD-000209)
  - `orders_2026-09-03_r1.csv:20` → `invalid_quantity` (ORD-000219)
- **Corrections in r2**:
  - ORD-000003: quantity 3 → 6.
  - ORD-000016: status → `cancelled`.
  - Both must come from `orders_2026-09-01_r2.csv` in `clean_orders`.
- **Late orders**: ORD-000041 to ORD-000048 exist only in r2 and must be in `clean_orders`.
- **Cross-file exact duplicate**: ORD-000136 appears in the 09-02 and 09-03 files and must be
  clean exactly once.
- **Standardised values**:
  - `' Electronics '` → `electronics` (ORD-000026)
  - `'Completed'` → `completed` (ORD-000031)
  - `'HOME'` → `home` (ORD-000131)
  - `'apparel '` → `apparel` (ORD-000229)
- **Completed vs cancelled**: 116 of the clean orders are `completed` and 8 are `cancelled`, so
  the summary's `SUM(orders)` = 116.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: project skeleton, dependencies and sample data.

- [X] T001 Create the directories `src/orders_pipeline/sql/`, `tests/` and `data/incoming/` at the project root, as laid out in plan.md
- [X] T002 Create `pyproject.toml`. It must contain:
  - project name `orders-pipeline` and `requires-python = ">=3.11"`;
  - dependency `duckdb>=1.1` and optional dev dependency `pytest`;
  - a setuptools src layout (`[tool.setuptools.packages.find] where = ["src"]`) that includes the `sql/*.sql` files as package data;
  - `[tool.pytest.ini_options] testpaths = ["tests"]`.
- [X] T003 [P] Create `.gitignore` ignoring `output/`, `.venv/`, `__pycache__/`, `.pytest_cache/` and `*.egg-info/`
- [X] T004 [P] Copy the 4 sample files from `../data/incoming/orders_*.csv` into `data/incoming/` byte for byte, with no edits. Commit them.
- [X] T005 [P] Create the package skeleton:
  - `src/orders_pipeline/__init__.py`, containing `__version__ = "0.1.0"`;
  - `src/orders_pipeline/__main__.py`, containing `import sys; from orders_pipeline.cli import main; sys.exit(main())`.
- [X] T006 Create the virtual environment and install: `uv venv && uv pip install -e ".[dev]"`. Confirm that `pytest -q` runs and finds no tests.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the file contract, raw ingestion, row-level standardisation and validation, the SQL
step runner, and the minimal CLI. Every story depends on these.

**⚠️ CRITICAL**: no user-story work can begin until this phase is complete.

### Tests for Foundational (write first, confirm they FAIL)

- [X] T007 [P] Create `tests/conftest.py` with these helpers:
  - `write_csv(dir, name, rows, header=EXPECTED_HEADER, raw_text=None)`: writes a fixture file, or writes `raw_text` exactly as given, for malformed cases;
  - `run_cli(*args) -> int`: calls `orders_pipeline.cli.main(list(args))` in-process;
  - `read_table(output_dir, name) -> list[tuple]`: uses `duckdb.sql(f"SELECT * FROM '{path}'").fetchall()` on the Parquet file;
  - `read_report(output_dir) -> dict`;
  - fixture `sample_input`: copies `data/incoming/*.csv` into `tmp_path / "in"`;
  - fixture `valid_row(**overrides)`: returns a valid 8-field row, for example `["ORD-1","C1","2026-09-01","P1","home","2","10.00","completed"]`.
- [X] T008 [P] Create `tests/test_file_contract.py`. It tests `orders_pipeline.ingest` directly, plus the CLI exit code.
  - Each of these names raises `ContractError(code="unexpected_file_name")`, and the CLI returns exit code 2:
    - `orders_latest.csv`
    - `orders_2026-09-01.csv`
    - `orders_2026-09-01_r0.csv`
    - `orders_2026-09-01_r01.csv`
    - `Orders_2026-09-01_r1.csv`
    - `orders_2026-09-01_r1.txt`
  - `orders_2026-02-30_r1.csv` gives `invalid_business_date`.
  - A header with a missing, extra, renamed or reordered column gives `invalid_header`.
  - An empty folder gives `no_input_files`.
  - A missing input folder gives `invalid_argument`.
  - Hidden files such as `.DS_Store`, and subfolders, are ignored.
  - A header-only file is accepted with 0 rows.
  - A UTF-8 BOM before the header is tolerated.
  - A completely blank line is skipped, not counted as a row, and counted in `blank_lines`. Physical line numbers still advance past it.
  - `discover_files` returns files sorted by `(business_date, revision as integer, name)`, so `r10` sorts after `r2`. The result does not depend on file modification times: set different mtimes with `os.utime`.
- [X] T009 [P] Create `tests/test_validation.py`. It loads fixtures through `ingest.load_raw_rows` and `transform.run_steps(con, upto="10")`, then queries `std_rows`.
  - There is one test per row-level reason code from Reference facts, codes 1–10.
  - Precedence: a row with a blank `order_id` and `quantity = "two"` gets `missing_order_id`.
  - Formats that must be rejected:
    - dates `2026-13-45`, `02/09/2026`, `2026-9-1` and `2026-09-01T00:00` are all `invalid_order_date`;
    - quantities `0`, `-2`, `two` and `1.5` are all `invalid_quantity`;
    - unit prices `-9.99`, `0`, `0.00`, `1e3`, `.5`, `1,000.00` and `9.999` are all `invalid_unit_price`.
  - `future_order_date` is judged against the business date in the file name only: `order_date = 2026-09-02` in `orders_2026-09-01_r1.csv` is rejected, and `order_date = 2026-08-31` in the same file is valid.
  - Standardising: `' Electronics '` becomes `electronics`, `'Completed'` becomes `completed` and `'HOME'` becomes `home`. `'  C1 '` is trimmed to `C1`. Blank `category` or `status` is invalid.
  - A valid row has `reject_reason IS NULL`, with typed `order_date` DATE, `quantity` INTEGER and `unit_price` DECIMAL(12,2).

### Implementation for Foundational

- [X] T010 Implement `src/orders_pipeline/ingest.py`:
  - `class ContractError(Exception)`, with attributes `code` and `message`;
  - constants `EXPECTED_HEADER` (the 8 columns) and `FILE_PATTERN` (the regex from Reference facts);
  - `@dataclass(frozen=True) InputFile(source_file: str, path: Path, business_date: date, revision: int)`;
  - `discover_files(input_dir) -> list[InputFile]`, following the rules in contracts/cli.md "Input contract". It skips names starting with `.` and subfolders, and sorts by `(business_date, revision, source_file)`.
  - `load_raw_rows(con, files)`. It reads each file with `open(path, newline="", encoding="utf-8-sig")` and `csv.reader`, checks that the header equals `EXPECTED_HEADER` (otherwise `invalid_header`), and skips `[]` records while counting them as `blank_lines`. It records `line_number = reader.line_num` and `field_count = len(record)`. Values 1–8 go in the 8 VARCHAR columns, padded with NULL when there are fewer. Extra fields are joined with `,` into `extra_values`. `row_id = f"{source_file}:{line_number}"`.
  - It creates the tables `input_files(source_file, entity, business_date, revision, row_count, blank_lines)` and `raw_rows(row_id, source_file, line_number, business_date, revision, field_count, order_id, customer_id, order_date, product_id, category, quantity, unit_price, status, extra_values)` with the types given in data-model.md. It bulk-inserts with `executemany`. No pandas.
- [X] T011 Implement `src/orders_pipeline/transform.py`:
  - `run_steps(con, upto: str | None = None)` lists `orders_pipeline/sql/*.sql` via `importlib.resources`, sorted by file name, and executes each file on `con`.
  - It stops after the step whose file-name prefix equals `upto`.
  - It logs one `step_done step=<name>` event per file.
- [X] T012 Implement `src/orders_pipeline/sql/10_standardise_validate.sql`, which creates `std_rows` from `raw_rows`.
  - Trim every value. Also apply `lower()` to `category` and `status`.
  - Set typed columns only when valid:
    - `order_date DATE` only if `regexp_full_match(v, '\d{4}-\d{2}-\d{2}')` and `TRY_CAST(v AS DATE)` is not NULL;
    - `quantity INTEGER` only if it matches `^[0-9]+$` and `TRY_CAST` succeeds (analysis U1: an overflow must reject the row, not crash the run);
    - `unit_price DECIMAL(12,2)` only if it matches `^[0-9]+(\.[0-9]{1,2})?$` and `TRY_CAST` succeeds.
  - Set `reject_reason` with a single `CASE` expression whose branches are in exactly the precedence order in Reference facts, codes 1–10.
  - Keep `row_id`, `source_file`, `line_number`, `business_date` and `revision`.
  - Never call `current_date` or `now()`.
- [X] T013 Implement `src/orders_pipeline/cli.py`.
  - Parse the flags with `argparse`: `--input` (required), `--output` (required) and `--max-reject-rate` (default `"0.10"`, parsed as `Decimal`, must satisfy 0 ≤ x ≤ 1; otherwise `invalid_argument`, exit code 2).
  - Provide `log_event(event, **kv)`. It writes one line, `<ISO timestamp> <LEVEL> <event> k=v ...` with keys sorted, to stderr and to `<output>/pipeline.log`.
  - `main(argv=None) -> int` opens `duckdb.connect()` in memory, runs `discover_files`, `load_raw_rows` and `run_steps`, and returns 0.
  - It maps `ContractError` to exit code 2 and logs `contract_error code=...`.
  - Publishing is added in US1, and the report and gate in US4.
- [X] T014 Run `pytest tests/test_file_contract.py tests/test_validation.py -q`. All must pass.

**Checkpoint**: raw ingestion and row validation work. User-story work can now begin.

---

## Phase 3: User Story 1 - Clean, de-duplicated orders table (Priority: P1) 🎯 MVP

**Goal**: produce `clean_orders` (one row per `order_id`) as Parquet and in `orders.duckdb`,
with exact duplicates collapsed, in-file and cross-date conflicts removed, and the latest revision
applied.

**Independent Test**: run the CLI on `data/incoming/`. `output/clean_orders.parquet` must have
124 rows, 124 distinct `order_id` values, the r2 values for ORD-000003 and ORD-000016, and
ORD-000041 to ORD-000048 present.

### Tests for User Story 1 (write first, confirm they FAIL)

- [X] T015 [P] [US1] Create `tests/test_dedup_revisions.py`. These are fixture tests that query `row_outcomes` and `clean_orders` after `run_steps`.
  - **Exact duplicates**:
    - Two identical rows in one file give 1 clean row, and the other row has `superseded` / `exact_duplicate` with `superseded_by` set.
    - An identical row in two files for different business dates gives 1 clean row, kept from the earlier business date.
    - Rows that differ only in `' Home '` vs `home` count as exact duplicates.
  - **Revisions**:
    - An order in r1 and, with a changed quantity, in r2 gives the r2 row clean (`source_file` is the r2 file, `revision = 2`). The r1 row is `superseded` / `older_revision`.
    - An order only in r1 stays clean.
    - An order only in r2 is clean.
    - `r10` beats `r2`.
  - **Invalid correction**: if the r2 version of an order is invalid (`quantity = -1`), the r1 row stays clean and the r2 row is `rejected` / `invalid_quantity`.
  - **In-file conflict**: the same `order_id` twice in one file with different content means both rows are `rejected` / `conflicting_order_id`.
  - **Cross-date conflict**: the same `order_id` with different content in `orders_2026-09-01_r1.csv` and `orders_2026-09-02_r1.csv` means the 09-01 row is clean and the 09-02 row is `rejected` / `conflicting_order_id`.
  - **One outcome per row**: every `raw_rows.row_id` appears exactly once in `row_outcomes`.
- [X] T016 [US1] Create `tests/test_sample_data.py`, with the US1 section only. Run the CLI on the `sample_input` fixture and check:
  - exit code 0;
  - `clean_orders.parquet` has 124 rows and 124 distinct `order_id` values;
  - ORD-000003 has quantity 6 and `source_file = orders_2026-09-01_r2.csv`;
  - ORD-000016 has status `cancelled`, from r2;
  - ORD-000041 to ORD-000048 are present;
  - ORD-000136 appears once;
  - none of ORD-000013, 000021, 000106, 000111, 000116, 000121, 000209 or 000219 is present;
  - `category` and `status` contain only allowed lower-case values;
  - `clean_orders` is sorted by `order_id`;
  - `orders.duckdb` table `clean_orders` has identical rows.

### Implementation for User Story 1

- [X] T017 [US1] Implement `src/orders_pipeline/sql/20_exact_duplicates.sql`.
  - Take the valid rows of `std_rows`, where `reject_reason IS NULL`.
  - Partition by the 8 standardised columns and number the rows with `ROW_NUMBER() OVER (... ORDER BY business_date ASC, revision DESC, source_file ASC, line_number ASC)`.
  - Row 1 goes into `dedup_rows`. The others go into `superseded_rows(row_id, reason='exact_duplicate', superseded_by=<row 1's row_id>)`.
- [X] T018 [US1] Implement `src/orders_pipeline/sql/30_in_file_conflicts.sql`.
  - Among `dedup_rows`, find the rows whose `COUNT(*) OVER (PARTITION BY source_file, order_id) > 1`.
  - Insert them into `conflict_rejects(row_id, reason='conflicting_order_id')`.
  - Create `step30_rows` with the remaining rows.
- [X] T019 [US1] Implement `src/orders_pipeline/sql/40_revisions.sql`.
  - For `step30_rows`, number the rows with `ROW_NUMBER() OVER (PARTITION BY business_date, order_id ORDER BY revision DESC)`.
  - Row 1 goes into `step40_rows`.
  - The others are inserted into `superseded_rows` with `reason='older_revision'`, and `superseded_by` is the winner's `row_id`.
- [X] T020 [US1] Implement `src/orders_pipeline/sql/50_cross_date_conflicts.sql`.
  - For `step40_rows`, number the rows with `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY business_date ASC)`.
  - Row 1 goes into `final_rows`.
  - The others are inserted into `conflict_rejects` with `reason='conflicting_order_id'`.
- [X] T021 [US1] Implement `src/orders_pipeline/sql/55_row_outcomes.sql`. It creates `row_outcomes(row_id, outcome, reason, superseded_by)` as a `UNION ALL` of four parts:
  - `final_rows` gives `clean` with NULL reason;
  - `std_rows` where `reject_reason IS NOT NULL` gives `rejected` with `reject_reason`;
  - `conflict_rejects` gives `rejected`;
  - `superseded_rows` gives `superseded`.
- [X] T022 [US1] Implement `src/orders_pipeline/sql/60_clean_orders.sql`.
  - It creates `clean_orders` from `final_rows` with these columns, in this order: `order_id, customer_id, order_date, product_id, category, quantity, unit_price, status, line_revenue, source_file, business_date, revision, line_number`.
  - `line_revenue = CAST(quantity * unit_price AS DECIMAL(18,2))`.
  - The rows are ordered by `order_id`.
- [X] T023 [US1] Implement `src/orders_pipeline/publish.py`.
  - A constant `PUBLISHED_TABLES: dict[str, str]` maps table name to `ORDER BY` clause. It starts with `{"clean_orders": "order_id"}`.
  - `write_outputs(con, target_dir)`: for each table, runs `COPY (SELECT * FROM t ORDER BY <key>) TO '<target_dir>/<t>.parquet' (FORMAT parquet)`.
  - It then runs `ATTACH '<target_dir>/orders.duckdb' AS out`, and for each table `CREATE OR REPLACE TABLE out.<t> AS SELECT * FROM t ORDER BY <key>`, followed by `DETACH out`.
- [X] T024 [US1] Update `src/orders_pipeline/cli.py`. After `run_steps`, create the `--output` folder and call `publish.write_outputs(con, output_dir)`. Log `outputs_written tables=...`.
- [X] T025 [US1] Run `pytest tests/test_dedup_revisions.py tests/test_sample_data.py -q`. All must pass.

**Checkpoint**: US1 is fully functional. `clean_orders` can be demonstrated on its own.

---

## Phase 4: User Story 2 - Quarantine of rejected rows with reasons (Priority: P1)

**Goal**: publish `rejected_orders` with raw values, source file, line number and one reason
code per row.

**Independent Test**: run the CLI on `data/incoming/`. `output/rejected_orders.parquet` must
contain exactly the 9 `source_file:line_number` → reason pairs listed in Reference facts, and
none of those orders may be in `clean_orders`.

### Tests for User Story 2 (write first, confirm they FAIL)

- [X] T026 [P] [US2] Create `tests/test_quarantine.py`. These are fixture tests on the CLI outputs.
  - The `rejected_orders` columns are exactly `source_file, line_number, business_date, revision, reject_reason, order_id, customer_id, order_date, product_id, category, quantity, unit_price, status, extra_values`.
  - Raw values are kept exactly as received, untrimmed: for example `quantity = ' two '` and `category = ' HOME '`.
  - `line_number` is the physical line: the header is line 1, and a blank line before a record shifts it.
  - A record with 10 fields becomes `malformed_row`, with `extra_values = "x,y"`.
  - A record with 6 fields becomes `malformed_row`, with `unit_price` and `status` NULL.
  - Both `conflicting_order_id` rows from an in-file conflict appear.
  - The rows are sorted by `(source_file, line_number)`.
  - No rejected `row_id` also appears in `clean_orders`.
- [X] T027 [US2] Extend `tests/test_sample_data.py` with a US2 section. `rejected_orders.parquet` must have exactly 9 rows, and its `(source_file, line_number, reject_reason)` must equal the 9 pairs in Reference facts. `orders.duckdb` must have identical rows.

### Implementation for User Story 2

- [X] T028 [US2] Implement `src/orders_pipeline/sql/61_rejected_orders.sql`.
  - It creates `rejected_orders` by joining `row_outcomes` (where `outcome = 'rejected'`) to `raw_rows` on `row_id`.
  - Columns: `source_file, line_number, business_date, revision, reject_reason (= row_outcomes.reason)`, the 8 raw VARCHAR columns from `raw_rows` (not standardised), and `extra_values`.
  - Ordered by `source_file, line_number`.
- [X] T029 [US2] Add `"rejected_orders": "source_file, line_number"` to `PUBLISHED_TABLES` in `src/orders_pipeline/publish.py`.
- [X] T030 [US2] Run `pytest tests/test_quarantine.py tests/test_sample_data.py -q`. All must pass.

**Checkpoint**: US1 and US2 both work. Every rejected row can be traced to its file and line.

---

## Phase 5: User Story 3 - Daily sales summary by date and category (Priority: P2)

**Goal**: publish `daily_sales_summary` built from completed clean orders only.

**Independent Test**: run the CLI on `data/incoming/`. `SUM(orders)` must be 116, and every row
must equal a hand aggregation of `clean_orders WHERE status = 'completed'`.

### Tests for User Story 3 (write first, confirm they FAIL)

- [X] T031 [P] [US3] Create `tests/test_summary.py`. These are fixture tests.
  - The columns are exactly `order_date, category, orders, units, revenue`.
  - There is one row per (`order_date`, `category`) among completed clean orders.
  - Cancelled orders are excluded from `orders`, `units` and `revenue`. A group whose orders are all cancelled produces no row.
  - Revenue is exact decimal arithmetic: 3 × `0.10` plus 1 × `0.20` gives `revenue = Decimal("0.50")`, never a float.
  - A revised order contributes only its latest values.
  - Rejected and superseded rows contribute nothing.
  - The rows are sorted by `(order_date, category)`.
- [X] T032 [US3] Extend `tests/test_sample_data.py` with a US3 section:
  - `SUM(orders)` = 116;
  - every summary row equals `SELECT order_date, category, COUNT(*), SUM(quantity), SUM(line_revenue) FROM clean_orders WHERE status='completed' GROUP BY 1,2`;
  - `orders.duckdb` has identical rows.

### Implementation for User Story 3

- [X] T033 [US3] Implement `src/orders_pipeline/sql/62_daily_sales_summary.sql`.
  - It creates `daily_sales_summary` as `SELECT order_date, category, COUNT(*)::BIGINT AS orders, SUM(quantity)::BIGINT AS units, CAST(SUM(line_revenue) AS DECIMAL(18,2)) AS revenue`.
  - The source is `clean_orders WHERE status = 'completed'`, grouped by `order_date, category` and ordered by `order_date, category`.
- [X] T034 [US3] Add `"daily_sales_summary": "order_date, category"` to `PUBLISHED_TABLES` in `src/orders_pipeline/publish.py`.
- [X] T035 [US3] Run `pytest tests/test_summary.py tests/test_sample_data.py -q`. All must pass.

**Checkpoint**: all three business outputs are published.

---

## Phase 6: User Story 4 - Trustworthy, repeatable runs with a run report (Priority: P2)

**Goal**:
- reconciliation invariants and the reject-rate gate;
- atomic publishing through staging;
- a deterministic `run_report.json` written on every run;
- the exit codes 0, 1 and 2 from contracts/cli.md.

**Independent Test**:
- Run the CLI twice on `data/incoming/`: the outputs and reports are identical.
- Run with `--max-reject-rate 0.05`: exit code 1, the earlier outputs are unchanged, and the report shows gate `failed`.
- Add `orders_latest.csv`: exit code 2 and error `unexpected_file_name`.

### Tests for User Story 4 (write first, confirm they FAIL)

- [X] T036 [P] [US4] Create `tests/test_gate_reconciliation.py`.
  - A fixture of 10 rows with 2 invalid rows (20%) gives exit code 1. No `*.parquet` or `orders.duckdb` file is created in a fresh output folder, and `run_report.json` has `gate.status = "failed"` and `outputs_published = false`.
  - **Exactly 10%**: 10 rows with 1 invalid row gives exit code 0 at threshold `0.10`.
  - `--max-reject-rate 0.05` on the same fixture gives exit code 1.
  - **Earlier outputs untouched**: a successful run followed by a failing run into the same `--output` leaves every Parquet and DuckDB file's bytes and `st_mtime_ns` unchanged.
  - `--max-reject-rate` values `1.5`, `-0.1` and `abc` give exit code 2 and error code `invalid_argument`.
  - **Reconciliation failure**: monkeypatch `transform.run_steps` to run steps up to `62`, delete one row from `row_outcomes`, then run step `70` (analysis I1: the checks must see the lost row). The result is exit code 1, `reconciliation.status = "failed"` and no outputs published.
  - `<output>/.staging/` does not exist after any run.
- [X] T037 [P] [US4] Create `tests/test_run_report.py`, checking against contracts/run-report.md.
  - The top-level keys are exactly `status, error, config, files, counts, reject_reasons, gate, reconciliation, outputs_published`.
  - `reject_reasons` has all 11 codes as keys, including those with a count of 0, and they sum to `counts.rows_rejected`.
  - `max_reject_rate`, `reject_rate` and `threshold` are strings. `reject_rate` is rounded half-up to 4 places.
  - `files` is sorted and holds base names only. `str(tmp_path)` must not appear anywhere in the report text.
  - The file is written with `sort_keys=True, indent=2` and a trailing newline.
  - On a contract error, the report has `status = "failed"`, `error.code` set, and gate and reconciliation `not_evaluated`.
  - `counts.rows_read == rows_clean + rows_rejected + rows_superseded`.
- [X] T038 [P] [US4] Create `tests/test_idempotency.py`.
  - Running the CLI twice into the same output gives identical rows from every published Parquet table and every `orders.duckdb` table, and `run_report.json` bytes are identical.
  - Copying the sample files into a second input folder in reverse order, with different mtimes (`os.utime`), gives identical outputs.
  - A pre-existing unrelated `orders.duckdb`, containing an extra table `junk`, or stale Parquet files in `--output` do not affect the results. After the run, `orders.duckdb` contains only the 3 published tables.
- [X] T039 [US4] Extend `tests/test_sample_data.py` with a US4 section. The `run_report.json` values must equal the table in `quickstart.md` step 2:
  - rows_read 138, rows_clean 124, rows_rejected 9, rows_superseded 5;
  - `superseded_by_reason` `{"exact_duplicate": 3, "older_revision": 2}`;
  - reject_reasons as listed in the quickstart;
  - `reject_rate` `"0.0652"`;
  - gate `passed`, reconciliation `passed`, `status` `succeeded`.

### Implementation for User Story 4

- [X] T040 [US4] Implement `src/orders_pipeline/sql/70_reconcile.sql`. It creates a one-row table `reconciliation` with these BOOLEAN columns:
  - `counts_balance`: `COUNT(raw_rows) = COUNT(row_outcomes)`, and the clean + rejected + superseded counts sum to it;
  - `row_ids_unique`;
  - `clean_order_id_unique`;
  - `clean_count_match`: `COUNT(clean_orders)` equals the clean outcome count (analysis G1);
  - `reasons_sum`: the rejected count equals `COUNT(rejected_orders)`;
  - `summary_orders_match`: `SUM(daily_sales_summary.orders)` equals the count of completed `clean_orders`, using `COALESCE(..., 0)`.
- [X] T041 [US4] Implement `src/orders_pipeline/report.py`.
  - `REJECT_CODES`: the 11 codes, in precedence order.
  - `build_report(*, status, error, max_reject_rate, files, counts, reject_reasons, gate, reconciliation, outputs_published) -> dict`, with the shape in contracts/run-report.md. All codes are present, decimals are strings, and `reject_rate` is rounded with `Decimal.quantize(Decimal("0.0001"), ROUND_HALF_UP)`.
  - `write_report(path, report)`: `json.dumps(report, sort_keys=True, indent=2) + "\n"`, written with UTF-8 encoding.
- [X] T042 [US4] Extend `src/orders_pipeline/publish.py`.
  - `evaluate_gate(rows_rejected, rows_read, threshold: Decimal) -> tuple[Decimal, bool]`. The rate is `Decimal(rows_rejected) / Decimal(rows_read)`, or `Decimal(0)` when `rows_read == 0`. It passes when `rate <= threshold`.
  - `publish(con, output_dir)`:
    - delete and recreate `<output>/.staging/`;
    - call `write_outputs(con, staging)`, which builds a new `orders.duckdb` in staging;
    - `os.replace` each staged file into `<output>/`;
    - remove `.staging/`.
  - A failed run never calls `publish`.
- [X] T043 [US4] Update `src/orders_pipeline/cli.py` to follow the full flow in contracts/cli.md:
  1. Parse and validate the arguments.
  2. Run discover, load and `run_steps`.
  3. Read the counts from `row_outcomes`, the per-reason counts and the `reconciliation` row.
  4. Evaluate the gate.
  5. If reconciliation and the gate both pass, publish, and the exit code is 0. Otherwise the exit code is 1 and nothing is published.
  6. On `ContractError`, the exit code is 2 and gate and reconciliation are `not_evaluated`.
  7. In every case, write `run_report.json` into `--output` (create it if it can be created).
  - Log the events `run_started`, `files_discovered`, `file_read`, `step_done`, `gate_evaluated`, `reconciliation_checked`, `outputs_published` or `outputs_withheld`, and `run_finished exit_code=`.
  - Never use absolute paths in the report.
- [X] T044 [US4] Run `pytest -q` (the full suite). All must pass.

**Checkpoint**: all user stories work, and every constitution guarantee is enforced by tests.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045 [P] Create `README.md` at the project root covering purpose, setup (`uv venv && uv pip install -e ".[dev]"`), the run command, the outputs, the exit codes, and links to `specs/001-daily-orders-pipeline/`.
- [X] T046 [P] Constitution audit. Run `grep -rnE "datetime\.now|date\.today|time\.time|current_date|now\(\)|random|/Users/|pandas" src/ tests/`. Nothing should be found, except log timestamps in `cli.log_event`. Fix any other hit.
- [X] T047 Run every step of `specs/001-daily-orders-pipeline/quickstart.md` by hand and confirm that each expected result matches.
- [X] T048 Performance check (SC-007), by hand. Generate about 5,000 valid rows across 5 files in a scratch folder, run the CLI, and confirm it finishes in under 1 minute. Record the timing in `README.md`. Do not add a timing assertion to the test suite, because Principle V forbids tests that depend on the clock.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup and blocks all stories.
- **US1 (Phase 3)**: depends on Foundational.
- **US2 (Phase 4)**: depends on Foundational, and on US1's `row_outcomes` (T021) and `publish.py` (T023).
- **US3 (Phase 5)**: depends on US1's `clean_orders` (T022) and `publish.py` (T023). It is independent of US2.
- **US4 (Phase 6)**: depends on US1, US2 and US3, because the reconciliation checks reference all three outputs.
- **Polish (Phase 7)**: depends on all stories.

### Within Each Story

- Tests are written and seen to FAIL, then the implementation, then the story's pytest run.
- The SQL steps depend on each other in number order: 20 → 30 → 40 → 50 → 55 → 60 → 61 → 62 → 70.
- `tests/test_sample_data.py` is extended by each story in turn (T016 → T027 → T032 → T039), so never edit it in parallel.
- `publish.py` is edited by T023, T029, T034 and T042 in that order, so never in parallel.

### Parallel Opportunities

- **Setup**: T003, T004 and T005 in parallel after T001.
- **Foundational tests**: T007, T008 and T009 in parallel.
- **Story tests**: T015 (US1), T026 (US2) and T031 (US3) can be written in parallel as soon as Foundational is done, because they are separate files.
- **US4 tests**: T036, T037 and T038 in parallel.
- **After US1**: US2 (T028 and T029) and US3 (T033 and T034) touch different SQL files. Only their `PUBLISHED_TABLES` edits need to be done one after the other.
- **Polish**: T045 and T046 in parallel.

---

## Parallel Example: User Story 4

```bash
# Write the three US4 test files together (all separate files):
Task: "Create tests/test_gate_reconciliation.py (T036)"
Task: "Create tests/test_run_report.py (T037)"
Task: "Create tests/test_idempotency.py (T038)"
```

## Parallel Example: after Foundational

```bash
# Test files for different stories can be drafted concurrently:
Task: "Create tests/test_dedup_revisions.py (T015)"
Task: "Create tests/test_quarantine.py (T026)"
Task: "Create tests/test_summary.py (T031)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (Setup), then Phase 2 (Foundational).
2. Phase 3 (US1), then **stop and validate**: `clean_orders` on the sample data has 124 unique orders, with the r2 corrections applied.

US1 alone is not yet constitution-complete, because the gate and the run report arrive in US4.
Do not treat the output as trusted until US4 is done.

### Incremental Delivery

1. Setup + Foundational: validated raw rows.
2. US1: clean orders (MVP demo).
3. US2: quarantine. Nothing disappears without a trace.
4. US3: daily sales summary.
5. US4: gate, reconciliation, atomic publish and run report. This is the first release the team can trust.
6. Polish: README, audit, quickstart, performance check.

---

## Notes

- **Deviation from plan.md**: the plan listed a single `sql/60_outputs.sql`. It is split here into `60_clean_orders.sql`, `61_rejected_orders.sql` and `62_daily_sales_summary.sql`, plus `55_row_outcomes.sql`, so that each story owns its own file. There is no change in behaviour.
- Verify that each test fails before you implement.
- Commit after each task or logical group.
- Never read the system clock in `src/` business logic or in `tests/`.
