# Quickstart: Daily Orders Pipeline

This is a validation guide proving the feature works end to end. The CLI is described in
[contracts/cli.md](./contracts/cli.md), the report in [contracts/run-report.md](./contracts/run-report.md),
and the tables in [data-model.md](./data-model.md).

## Prerequisites

- Python 3.11+ and `uv`. Plain `pip` also works.
- The 4 sample files copied into the project. Run this once from the project root:

  ```bash
  mkdir -p data/incoming && cp ../data/incoming/orders_*.csv data/incoming/
  ```

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 1. Tests

```bash
pytest -q
```

**Expected**: all tests pass. The tests need no network access, and repeated runs give the same
result.

## 2. Run on the sample data

```bash
python -m orders_pipeline --input data/incoming --output output --max-reject-rate 0.10
echo "exit=$?"
```

**Expected**: `exit=0`. The `output/` folder contains the files listed in contracts/cli.md, and
`output/run_report.json` shows:

| field | value |
|---|---|
| `counts.rows_read` | 138 |
| `counts.rows_clean` | 124 |
| `counts.rows_rejected` | 9 |
| `counts.rows_superseded` | 5 (`exact_duplicate` 3, `older_revision` 2) |
| `reject_reasons` | `invalid_quantity` 3, `invalid_order_date` 2, `missing_customer_id` 1, `missing_order_id` 1, `invalid_unit_price` 1, `future_order_date` 1, all others 0 |
| `gate` | `reject_rate` `0.0652`, `status` `passed` |
| `reconciliation.status` | `passed` |

## 3. Spot-check the outputs

```bash
python - <<'EOF'
import duckdb
con = duckdb.connect("output/orders.duckdb", read_only=True)
print(con.sql("SELECT count(*), count(DISTINCT order_id) FROM clean_orders"))
print(con.sql("SELECT reject_reason, source_file, line_number FROM rejected_orders"))
print(con.sql("SELECT sum(orders) FROM daily_sales_summary"))
EOF
```

**Expected**:
- `clean_orders` has 124 rows and 124 distinct `order_id` values.
- `rejected_orders` lists the 9 planted rows.
- The summary's `sum(orders)` is 116, which is the number of completed clean orders. The 8
  cancelled orders are not included.
- In `clean_orders`, the two corrected 2026-09-01 orders come from `orders_2026-09-01_r2.csv`.

## 4. Idempotency

```bash
cp output/run_report.json /tmp/report1.json
python -m orders_pipeline --input data/incoming --output output
diff /tmp/report1.json output/run_report.json && echo "report identical"
```

**Expected**: the reports are identical. The tests also compare every table row by row.

## 5. Quality gate

```bash
python -m orders_pipeline --input data/incoming --output output --max-reject-rate 0.05
echo "exit=$?"
```

**Expected**: `exit=1`, because 6.52% is above 5%. `run_report.json` shows `gate.status`
`failed` and `outputs_published` `false`. The Parquet and DuckDB files from step 4 are unchanged,
with the same modification time.

## 6. Contract failure

```bash
mkdir -p /tmp/bad_in && cp data/incoming/*.csv /tmp/bad_in/ && touch /tmp/bad_in/orders_latest.csv
python -m orders_pipeline --input /tmp/bad_in --output /tmp/bad_out
echo "exit=$?"
```

**Expected**: `exit=2`. `/tmp/bad_out/run_report.json` shows the error code
`unexpected_file_name`, and no data outputs are written.
