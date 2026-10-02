# Data Model: Daily Orders Pipeline

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

All names are `snake_case` (constitution, Naming and Layout). Published tables are
`clean_orders`, `rejected_orders` and `daily_sales_summary`. The other tables are intermediate:
they exist only in the in-memory DuckDB connection during a run and are never published.

## Row lifecycle

```text
input file ──► raw_rows ──► std_rows ──┬─ reject_reason set ─────────────────────────► rejected
                                       └─ valid ─► exact dedup ──┬─ copy ───────────────► superseded
                                                                 └─ representative
                                                                    ─► in-file conflict ─┬─ yes ─► rejected
                                                                                         └─ no
                                                                    ─► revision resolve ─┬─ older ─► superseded
                                                                                         └─ latest
                                                                    ─► cross-date ───────┬─ later date ─► rejected
                                                                                         └─ earliest ───► clean
```

Every `row_id` ends in exactly one terminal state: `clean`, `rejected` or `superseded`.

## Intermediate tables

### `input_files`
One row per file found in the input folder. It is built before any data is read.

| column | type | notes |
|---|---|---|
| `source_file` | VARCHAR | Base name only, e.g. `orders_2026-09-01_r2.csv`. No directory path. |
| `entity` | VARCHAR | Always `orders`. |
| `business_date` | DATE | From the file name. Must be a real calendar date. |
| `revision` | INTEGER | From `r<N>`. Must be 1 or more. |
| `row_count` | INTEGER | Number of non-blank data records. |
| `blank_lines` | INTEGER | Completely empty lines. They are skipped, not counted as rows, and are reported. |

Contract errors fail the whole run (see [contracts/cli.md](./contracts/cli.md)):
- a file name that does not match `^orders_(\d{4}-\d{2}-\d{2})_r([1-9][0-9]*)\.csv$`;
- a business date that is not a real calendar date;
- a header that is not exactly the 8 expected columns, in order;
- no `.csv` files found.

### `raw_rows`
One row per data record exactly as read. Every value is kept as a string.

| column | type | notes |
|---|---|---|
| `row_id` | VARCHAR | `source_file:line_number`. This is the primary key. |
| `source_file` | VARCHAR | |
| `line_number` | INTEGER | Physical line in the file. The header is line 1. |
| `business_date` | DATE | Taken from `input_files`. |
| `revision` | INTEGER | Taken from `input_files`. |
| `field_count` | INTEGER | Number of fields the CSV parser found. |
| `order_id` … `status` | VARCHAR ×8 | Raw values, not trimmed. NULL when the record has fewer fields. |
| `extra_values` | VARCHAR | Fields beyond the 8th, joined with `,`. NULL otherwise. |

### `std_rows`
`raw_rows` plus standardised values and the result of row-level validation.

| column | type | rule |
|---|---|---|
| `order_id`, `customer_id`, `product_id` | VARCHAR | Trimmed. |
| `category`, `status` | VARCHAR | Trimmed and lower-cased. |
| `order_date` | DATE | Set only if the value matches `YYYY-MM-DD` and is a real date. |
| `quantity` | INTEGER | Set only if the value is a whole number of 1 or more and fits in an INTEGER (`TRY_CAST`). Otherwise the row is rejected, never crashed. |
| `unit_price` | DECIMAL(12,2) | Set only if the value is a number greater than 0 with at most 2 decimal places and fits in DECIMAL(12,2) (`TRY_CAST`). |
| `reject_reason` | VARCHAR | The first failing rule in FR-012 order, or NULL if the row is valid. |

Row-level reason codes are assigned in this fixed precedence (FR-012):

| # | code | condition |
|---|---|---|
| 1 | `malformed_row` | `field_count <> 8` |
| 2 | `missing_order_id` | trimmed `order_id` is blank |
| 3 | `missing_customer_id` | trimmed `customer_id` is blank |
| 4 | `missing_product_id` | trimmed `product_id` is blank |
| 5 | `invalid_order_date` | does not match `^\d{4}-\d{2}-\d{2}$`, or is not a real date |
| 6 | `future_order_date` | `order_date > business_date` |
| 7 | `invalid_quantity` | does not match `^[0-9]+$`, or is less than 1 |
| 8 | `invalid_unit_price` | does not match `^[0-9]+(\.[0-9]{1,2})?$`, or is 0 or less |
| 9 | `invalid_category` | not in {`electronics`, `home`, `grocery`, `apparel`} |
| 10 | `invalid_status` | not in {`completed`, `cancelled`} |
| 11 | `conflicting_order_id` | assigned later, by the steps in [research.md](./research.md) R3 |

### `row_outcomes`
One row per `row_id`. This table is the basis for reconciliation.

| column | type | notes |
|---|---|---|
| `row_id` | VARCHAR | Unique. |
| `outcome` | VARCHAR | `clean`, `rejected` or `superseded`. |
| `reason` | VARCHAR | For rejected rows, the reject code. For superseded rows, `exact_duplicate` or `older_revision`. For clean rows, NULL. |
| `superseded_by` | VARCHAR | For superseded rows, the `row_id` of the row that won. NULL otherwise. |

## Published tables

### `clean_orders`
One row per `order_id` (FR-018). Sorted by `order_id`.

| column | type | notes |
|---|---|---|
| `order_id` | VARCHAR | Unique. |
| `customer_id` | VARCHAR | |
| `order_date` | DATE | |
| `product_id` | VARCHAR | |
| `category` | VARCHAR | One of the 4 allowed values. |
| `quantity` | INTEGER | 1 or more. |
| `unit_price` | DECIMAL(12,2) | Greater than 0. |
| `status` | VARCHAR | `completed` or `cancelled`. |
| `line_revenue` | DECIMAL(18,2) | `quantity * unit_price`. |
| `source_file` | VARCHAR | The file the kept row came from. |
| `business_date` | DATE | |
| `revision` | INTEGER | |
| `line_number` | INTEGER | |

### `rejected_orders`
One row per rejected input row (FR-019). Sorted by `source_file`, then `line_number`.

| column | type | notes |
|---|---|---|
| `source_file` | VARCHAR | |
| `line_number` | INTEGER | |
| `business_date` | DATE | |
| `revision` | INTEGER | |
| `reject_reason` | VARCHAR | A code from the table above. |
| `order_id` … `status` | VARCHAR ×8 | Raw values, exactly as received. |
| `extra_values` | VARCHAR | Only for `malformed_row`. |

### `daily_sales_summary`
One row per (`order_date`, `category`) among clean orders with `status = 'completed'`
(FR-020, Q1). Sorted by `order_date`, then `category`.

| column | type | notes |
|---|---|---|
| `order_date` | DATE | |
| `category` | VARCHAR | |
| `orders` | BIGINT | `COUNT(*)` |
| `units` | BIGINT | `SUM(quantity)` |
| `revenue` | DECIMAL(18,2) | `SUM(line_revenue)` |

## Invariants checked every run

1. `COUNT(raw_rows) = COUNT(row_outcomes)`, and `row_id` is unique in `row_outcomes`.
2. `rows_read = rows_clean + rows_rejected + rows_superseded`.
3. `rows_clean = COUNT(clean_orders)` (`clean_count_match`), and `order_id` is unique in `clean_orders` (`clean_order_id_unique`).
4. `rows_rejected = COUNT(rejected_orders)`, and it equals the sum of the per-reason counts.
5. The summary's `SUM(orders)` equals the number of clean orders with status `completed`.

If any invariant fails, the run fails with reconciliation status `failed` (exit code 1).
