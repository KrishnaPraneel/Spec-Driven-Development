# Daily Orders Pipeline

This pipeline turns order-management CSV extracts (`orders_<YYYY-MM-DD>_r<N>.csv`) into three
tables:

- `clean_orders`: one row per order, with duplicates removed and the latest revision applied.
- `rejected_orders`: every rejected row, with the raw values, the source file and line, and one
  reason code.
- `daily_sales_summary`: orders, units and revenue by order date and category, counting
  completed orders only.

Every input row is accounted for, and re-running on the same files gives the same results.

- Spec, plan and design: [`specs/001-daily-orders-pipeline/`](specs/001-daily-orders-pipeline/)
- Principles: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## Run

```bash
python -m orders_pipeline --input data/incoming --output output --max-reject-rate 0.10
```

The run fails when the share of rejected rows is **strictly greater** than
`--max-reject-rate` (default `0.10`). A failed run publishes nothing and leaves earlier outputs
unchanged.

## Outputs (in `--output`)

| File | Contents |
|---|---|
| `clean_orders.parquet` | Clean orders, sorted by `order_id` |
| `rejected_orders.parquet` | Rejected rows, sorted by `source_file, line_number` |
| `daily_sales_summary.parquet` | Summary rows, sorted by `order_date, category` |
| `orders.duckdb` | The same three tables |
| `run_report.json` | Files read, row counts, reject reasons, gate and reconciliation results. It is written on every run and has no timestamps. |
| `pipeline.log` | Plain-text log, one line per event, overwritten each run |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. All outputs were replaced. |
| 1 | The reject rate was above the threshold, or reconciliation failed. Nothing was published. |
| 2 | Contract or usage error, such as an unexpected file name, a bad header, no input files, or a bad flag. |

## How it works

Python's standard-library `csv` module finds the files, checks their names and headers, and
loads the raw string values into DuckDB. All the business logic is in the numbered SQL steps
in `src/orders_pipeline/sql/`, which run in file-name order:

- **10**: validate
- **20**: exact duplicates
- **30**: conflicts within a file
- **40**: latest revision wins
- **50**: conflicts across business dates
- **55**: row outcomes
- **60–62**: output tables
- **70**: reconciliation

## Performance

5,000 rows in 5 files took 5.7 s wall-clock on a laptop (macOS, Python 3.12, DuckDB 1.x). The
target is under 1 minute.
