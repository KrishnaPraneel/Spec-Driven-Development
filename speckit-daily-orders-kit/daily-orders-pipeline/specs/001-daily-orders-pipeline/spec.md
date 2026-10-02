# Feature Specification: Daily Orders Pipeline

**Feature Branch**: `001-daily-orders-pipeline`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Daily orders pipeline. The commerce analytics team receives order extracts from the order-management system as CSV files (orders_<business-date>_r<revision>.csv, columns: order_id, customer_id, order_date, product_id, category, quantity, unit_price, status). They need (1) a clean orders table with one row per order, (2) a quarantine table with every rejected row and the reason it was rejected, and (3) a daily sales summary by order date and category (orders, units, revenue). The team must be able to trust the numbers: nothing may disappear without a trace, and re-running must never change the results. Out of scope: scheduling, orchestration, cloud storage, dashboards."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean, de-duplicated orders table (Priority: P1)

An analyst on the commerce analytics team points the pipeline at a folder of order extract files
and runs it. They get one clean orders table with exactly one row per order. Duplicate rows have
been removed, corrections from later revisions have been applied, and text values such as
category and status have been standardised, so the analyst can query the orders directly without
cleaning them first.

**Why this priority**: every other output is built from the clean orders. Without a trusted
one-row-per-order table there is nothing to summarise.

**Independent Test**: run the pipeline on the four sample files and check that the clean orders
table has one row per order_id, contains no invalid rows, and reflects the r2 corrections for
2026-09-01.

**Acceptance Scenarios**:

1. **Given** a file containing the same row twice, **When** the pipeline runs, **Then** the clean
   table contains that order once and the second copy is counted as superseded.
2. **Given** an order that appears in `orders_2026-09-01_r1.csv` and, with a different quantity,
   in `orders_2026-09-01_r2.csv`, **When** the pipeline runs, **Then** the clean table holds the
   r2 version and the r1 version is counted as superseded.
3. **Given** orders that appear only in r2 of a business date (late-arriving), **When** the
   pipeline runs, **Then** they are included in the clean table alongside the r1-only orders.
4. **Given** a category of `' Electronics '` or a status of `'Completed'`, **When** the pipeline
   runs, **Then** the clean table stores `electronics` and `completed`.
5. **Given** an exact copy of a 2026-09-02 order inside the 2026-09-03 file, **When** the pipeline
   runs, **Then** the order appears once in the clean table.

---

### User Story 2 - Quarantine of rejected rows with reasons (Priority: P1)

The analyst can see every row that was rejected, which file and line it came from, the original
values exactly as received, and a reason code explaining why. They use this to raise data issues
with the order-management team.

**Why this priority**: the team's main requirement is that nothing disappears without a trace.
Quarantine is what makes the clean table trustworthy, so it ships with Story 1.

**Independent Test**: run the pipeline on the sample files and check that each planted bad row
(negative or zero or non-numeric quantity, impossible date, wrongly formatted date, future date,
blank customer_id, blank order_id, negative price) appears in the quarantine table with the
expected reason code, and that none of them appears in the clean table.

**Acceptance Scenarios**:

1. **Given** a row with `quantity = -2`, `0` or `two`, **When** the pipeline runs, **Then** it is
   quarantined with reason `invalid_quantity`.
2. **Given** a row with `order_date = 2026-13-45` or `02/09/2026`, **When** the pipeline runs,
   **Then** it is quarantined with reason `invalid_order_date` and is not re-parsed.
3. **Given** a row in `orders_2026-09-03_r1.csv` with `order_date = 2026-12-25`, **When** the
   pipeline runs, **Then** it is quarantined with reason `future_order_date`.
4. **Given** a row with a blank `customer_id`, **When** the pipeline runs, **Then** it is
   quarantined with reason `missing_customer_id`.
5. **Given** a row that fails several rules, **When** the pipeline runs, **Then** it appears in
   quarantine once, with the single reason code chosen by the fixed precedence order (FR-012).

---

### User Story 3 - Daily sales summary by date and category (Priority: P2)

The analyst gets a summary with one row per order date and category, showing the number of
orders, the units sold and the revenue. They can use it for daily reporting without writing any
aggregation themselves.

**Why this priority**: this is the business-facing output, but it is derived entirely from the
clean orders and can be produced once Story 1 works.

**Independent Test**: run the pipeline on the sample files and compare the summary against totals
computed by hand from the clean orders table.

**Acceptance Scenarios**:

1. **Given** the clean orders table, **When** the summary is produced, **Then** there is exactly
   one row per (order_date, category) combination among the completed clean orders, and the orders,
   units and revenue in each row match that group.
2. **Given** cancelled orders in the clean table, **When** the summary is produced, **Then** they
   are left out of the summary completely (orders, units and revenue), but remain in the clean
   orders table.
3. **Given** an order that was corrected in a later revision, **When** the summary is produced,
   **Then** the summary uses only the corrected values.

---

### User Story 4 - Trustworthy, repeatable runs with a run report (Priority: P2)

After each run the analyst reads a run report that says which files were read, how many rows
were read, kept, rejected and superseded, how many rows were rejected for each reason, and
whether the quality gate passed. Running the pipeline again on the same files gives exactly the
same results. If too many rows are bad, the run fails and publishes nothing, so a bad batch never
reaches reports.

**Why this priority**: this is what lets the team trust the numbers. It depends on Stories 1 to 3
existing.

**Independent Test**: run the pipeline twice on the sample files and compare the outputs; check
that the run report's counts balance; then run it on a fixture where more than 10% of rows are
invalid and check that the run fails and no clean or summary output is published.

**Acceptance Scenarios**:

1. **Given** the same input files and configuration, **When** the pipeline runs twice, **Then**
   the clean, quarantine and summary outputs are identical (same rows, values and order).
2. **Given** any run, **When** it finishes, **Then** the report shows
   `rows_read = rows_clean + rows_rejected + rows_superseded`. If the equation does not balance,
   the run fails.
3. **Given** a batch where more than 10% of rows read are rejected, **When** the pipeline runs,
   **Then** the run fails, no clean or summary output is published, outputs from an earlier
   successful run are left untouched, and the run report is still written with the gate marked
   failed.
4. **Given** the same files copied into the input folder in a different order or at different
   times, **When** the pipeline runs, **Then** the results are identical.

---

### Edge Cases

- **Unexpected file name**: a file in the input folder that does not match
  `orders_<YYYY-MM-DD>_r<N>.csv`, or whose business date in the name is not a real calendar date,
  makes the whole run fail before any data is processed.
- **Wrong columns**: a file whose header is not exactly the eight expected columns makes the whole
  run fail and names the file.
- **Empty input folder**: the run fails with a clear message saying no input files were found.
- **Header-only file**: accepted. It adds zero rows and is listed in the run report.
- **Row with the wrong number of fields**: quarantined with reason `malformed_row`.
- **Invalid correction**: if a later revision's version of an order is rejected, it does not
  replace the earlier valid version. The earlier version stays in the clean table and the invalid
  row is quarantined.
- **Same order_id in files for different business dates with different content** (not an exact
  duplicate and not a revision): the valid row from the earliest business date is kept, and each
  row from a later business date is quarantined with reason `conflicting_order_id`.
- **Same order_id twice within one file with different content**: both rows are quarantined with
  reason `conflicting_order_id`, because neither can be chosen without guessing.
- **Order dated earlier than the file's business date**: accepted (for example, an order from
  2026-09-02 that also appears in the 2026-09-03 file).
- **Reject rate exactly 10%**: the run passes. Only a rate strictly above the threshold fails.
- **Unknown category or status** after standardising: quarantined with reason `invalid_category`
  or `invalid_status`.

## Requirements *(mandatory)*

### Functional Requirements

**Input contract**

- **FR-001**: The pipeline MUST read every file in a configured input folder. Each file MUST be
  named `orders_<YYYY-MM-DD>_r<N>.csv`, where the date is the business date and `N` is a positive
  whole-number revision. Any other file name MUST fail the run before any data is processed.
- **FR-002**: Each file MUST have a header row with exactly these columns: `order_id`,
  `customer_id`, `order_date`, `product_id`, `category`, `quantity`, `unit_price`, `status`.
  A missing, extra or renamed column MUST fail the run.
- **FR-003**: The input folder, the output location and the reject-rate threshold MUST be
  configurable without changing the pipeline. The threshold defaults to 10%.

**Row validation and standardisation**

- **FR-004**: Leading and trailing spaces MUST be trimmed from every value. `category` and
  `status` MUST also be lower-cased. No other value is altered.
- **FR-005**: `order_id`, `customer_id` and `product_id` MUST be non-blank. Otherwise the row is
  rejected with `missing_order_id`, `missing_customer_id` or `missing_product_id`.
- **FR-006**: `order_date` MUST be a real calendar date written as `YYYY-MM-DD`. Otherwise the
  row is rejected with `invalid_order_date`. Other date formats MUST NOT be re-interpreted.
- **FR-007**: `order_date` MUST NOT be later than the business date in the file name. Otherwise
  the row is rejected with `future_order_date`. This check MUST NOT use today's date.
- **FR-008**: `quantity` MUST be a whole number of 1 or more. Otherwise the row is rejected with
  `invalid_quantity`.
- **FR-009**: `unit_price` MUST be a number greater than 0 with at most 2 decimal places.
  Otherwise the row is rejected with `invalid_unit_price`.
- **FR-010**: After standardising, `category` MUST be one of `electronics`, `home`, `grocery`,
  `apparel`, and `status` MUST be one of `completed`, `cancelled`. Otherwise the row is rejected
  with `invalid_category` or `invalid_status`. A blank value counts as invalid.
- **FR-011**: A row whose number of fields does not match the header MUST be rejected with
  `malformed_row`.
- **FR-012**: Each rejected row MUST carry exactly one reason code, chosen as the first failing
  rule in this order: `malformed_row`, `missing_order_id`, `missing_customer_id`,
  `missing_product_id`, `invalid_order_date`, `future_order_date`, `invalid_quantity`,
  `invalid_unit_price`, `invalid_category`, `invalid_status`, `conflicting_order_id`.
- **FR-013**: Rejected rows MUST NOT be corrected, defaulted or partially loaded.

**De-duplication and revisions**

- **FR-014**: Rows that are identical in all eight columns after standardising MUST be treated as
  exact duplicates, whether they are in the same file or in different files. One copy is kept
  and the others are counted as superseded.
- **FR-015**: When the same `order_id` appears in more than one revision of the same business
  date, the valid row from the highest revision MUST be kept and the valid rows from lower
  revisions counted as superseded. Revision order MUST come from the `r<N>` number in the file
  name only.
- **FR-016**: An order present only in a lower revision MUST be kept. A later revision adds and
  corrects orders but never removes them.
- **FR-017**: When the same `order_id` appears twice in one file with different content, both
  rows MUST be rejected with `conflicting_order_id`.
- **FR-017a**: When the same `order_id` appears with different content in files for different
  business dates, the valid row from the earliest business date MUST be kept, and the rows from
  later business dates MUST be rejected with `conflicting_order_id`. Within each business date,
  FR-015 is applied first.

**Outputs**

- **FR-018**: The pipeline MUST produce a clean orders table with exactly one row per `order_id`,
  holding the standardised values plus the source file and revision of the row that was kept,
  and the line revenue (`quantity × unit_price`).
- **FR-019**: The pipeline MUST produce a quarantine table with one row per rejected input row,
  holding the original values exactly as received, the source file name, the line number in
  that file, and the reason code.
- **FR-020**: The pipeline MUST produce a daily sales summary with one row per (`order_date`,
  `category`), holding the order count, units (sum of quantity) and revenue (sum of line
  revenue, to 2 decimal places), built only from the clean orders whose status is `completed`.
  Cancelled orders MUST NOT count toward any summary figure.
- **FR-021**: Every output MUST be sorted in a fixed, documented order, so that repeated runs
  produce identical outputs.
- **FR-022**: Every run MUST replace all outputs completely. Nothing is appended to the results
  of an earlier run.

**Trust and reporting**

- **FR-023**: Every run MUST check `rows_read = rows_clean + rows_rejected + rows_superseded`
  and fail if it does not hold.
- **FR-024**: A run MUST fail when `rows_rejected / rows_read` is strictly greater than the
  configured threshold. A failed run MUST NOT publish the clean table or the summary, and MUST
  leave any outputs from an earlier successful run unchanged.
- **FR-025**: Every run, including a failed one, MUST write a run report listing: each file read
  with its business date, revision and row count; rows read, clean, rejected and superseded;
  the number of rejected rows per reason code; the reject rate and threshold; the gate status;
  and the reconciliation result.
- **FR-026**: The pipeline MUST write a plain-text log with one line per event.
- **FR-027**: Re-running on the same files and configuration MUST give identical clean,
  quarantine and summary outputs, regardless of file arrival order or timestamps.

### Key Entities

- **Order extract file**: one CSV delivered by the order-management system. Identified by its
  business date and revision number, both taken from the file name.
- **Input row**: one data line in an extract file, identified by file name and line number. It
  ends up as a clean order, a rejected row, or a superseded row.
- **Clean order**: one validated, standardised order, unique by `order_id`. Records which file
  and revision it came from.
- **Rejected row**: an input row that failed validation, kept exactly as received, with its
  source file, line number and reason code.
- **Daily sales summary row**: totals for one order date and category: orders, units, revenue.
- **Run report**: the record of one run: files read, row counts, reject reasons, reject rate,
  gate status and reconciliation result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of input rows are accounted for in every run: each row is clean, rejected or
  superseded, and the counts balance exactly.
- **SC-002**: Running the pipeline twice on the same files gives outputs that are identical in
  every row and value, in 10 out of 10 repeated runs.
- **SC-003**: On the provided sample data, all 9 planted invalid rows are quarantined with the
  expected reason code, and 0 of them appear in the clean table or summary.
- **SC-004**: On the provided sample data, all 3 exact duplicates and both r2 corrections are
  resolved: the clean table contains no repeated `order_id`, and each corrected order shows the
  r2 values.
- **SC-005**: An analyst can find out why any given row was rejected, and which file and line it
  came from, in under 1 minute using only the quarantine table and run report.
- **SC-006**: A batch with more than 10% invalid rows never reaches the clean table or summary,
  in 100% of cases.
- **SC-007**: A full run on a day's files (a few thousand rows) completes in under 1 minute on a
  standard laptop.

## Assumptions

- The pipeline is run by hand by an analyst or engineer. Scheduling, orchestration, cloud
  storage and dashboards are out of scope.
- Every run processes all files currently in the input folder and rebuilds all outputs from
  scratch. There is no incremental processing.
- Allowed categories are `electronics`, `home`, `grocery`, `apparel`, and allowed statuses are
  `completed`, `cancelled`, based on the sample data. New values are rejected until the lists
  are updated.
- "Future" means later than the business date in the file name, not later than today, so
  results do not depend on when the pipeline is run.
- An order may legitimately appear in a file for a later business date than its order_date.
- Free items are not expected, so a unit price of 0 is treated as invalid.
- "Sales" means completed orders only, so cancelled orders are left out of the summary.
- Revenue is `quantity × unit_price`, in a single currency, with no tax, discount or refund
  adjustments.
- Files are UTF-8 CSV with a comma separator and a header row.
- The reject-rate denominator is all rows read, including rows later counted as superseded.
