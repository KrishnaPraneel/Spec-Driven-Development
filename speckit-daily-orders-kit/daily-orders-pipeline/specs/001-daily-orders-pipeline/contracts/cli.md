# Contract: Command-Line Interface

## Invocation

```text
python -m orders_pipeline --input <dir> --output <dir> [--max-reject-rate <fraction>]
```

| flag | required | default | meaning |
|---|---|---|---|
| `--input` | yes | – | Folder containing `orders_<YYYY-MM-DD>_r<N>.csv` files. Only its top level is read. |
| `--output` | yes | – | Folder for the outputs. It is created if missing. |
| `--max-reject-rate` | no | `0.10` | A decimal fraction from 0 to 1. The run fails when the reject rate is strictly greater than this value. |

Relative paths are resolved against the current working directory. No path is hardcoded in the
package (constitution VI).

## Input contract

- Every entry in the input folder, other than subfolders and hidden files (names starting with
  `.`), MUST match `orders_<YYYY-MM-DD>_r<N>.csv`, where `N` is a whole number of 1 or more with
  no leading zeros. A non-matching entry fails the run.
- The header must be exactly
  `order_id,customer_id,order_date,product_id,category,quantity,unit_price,status`.
- Encoding is UTF-8. A UTF-8 byte-order mark at the start of the file is tolerated.
- The delimiter is a comma, and quoting follows RFC 4180.
- Files are processed in sorted order: `business_date`, then `revision`, then name. Results do
  not depend on file modification times.

## Exit codes

| code | meaning | outputs published? | run report written? |
|---|---|---|---|
| 0 | Success: gate passed and reconciliation passed. | yes, all replaced | yes, `status: "succeeded"` |
| 1 | Data failure: reject rate above the threshold, or reconciliation mismatch. | no; earlier outputs left untouched | yes, `status: "failed"` |
| 2 | Contract or usage error: bad file name, bad header, no input files, bad flag value, input folder missing. | no | yes if the output folder is usable, with `status: "failed"` and `error` set |

## Output folder layout (on success)

```text
<output>/
├── clean_orders.parquet
├── rejected_orders.parquet
├── daily_sales_summary.parquet
├── orders.duckdb            # the same three tables
├── run_report.json          # see run-report.md
└── pipeline.log             # plain text, one line per event
```

`<output>/.staging/` is used during a run and removed at the end. Table schemas are in
[../data-model.md](../data-model.md).

## Log format

The log is plain text with one line per event, written to `pipeline.log` and to stderr. `pipeline.log` is overwritten on each run:

```text
<ISO-8601 local timestamp> <LEVEL> <event> key=value key=value ...
```

For example: `... INFO file_read file=orders_2026-09-01_r1.csv rows=42 blank_lines=0`. The log is
diagnostic only. It is not a data output, so its timestamps do not affect idempotency.
