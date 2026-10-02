# Contract: `run_report.json`

The report is written on every run, including failed ones (constitution VIII, FR-025). It is
UTF-8 JSON with keys sorted and a 2-space indent. It contains no timestamps and no absolute
paths, so it is byte-identical across re-runs on the same input and configuration.

## Shape

```json
{
  "status": "succeeded",
  "error": null,
  "config": {
    "max_reject_rate": "0.10"
  },
  "files": [
    {"source_file": "orders_2026-09-01_r1.csv", "business_date": "2026-09-01", "revision": 1, "rows": 42, "blank_lines": 0}
  ],
  "counts": {
    "rows_read": 138,
    "rows_clean": 124,
    "rows_rejected": 9,
    "rows_superseded": 5,
    "superseded_by_reason": {"exact_duplicate": 3, "older_revision": 2}
  },
  "reject_reasons": {"future_order_date": 1, "invalid_order_date": 2, "...": 0},
  "gate": {
    "reject_rate": "0.0652",
    "threshold": "0.10",
    "status": "passed"
  },
  "reconciliation": {
    "status": "passed",
    "checks": {"counts_balance": true, "row_ids_unique": true, "clean_order_id_unique": true, "clean_count_match": true, "reasons_sum": true, "summary_orders_match": true}
  },
  "outputs_published": true
}
```

## Field rules

| field | rule |
|---|---|
| `status` | `succeeded` or `failed`. |
| `error` | `null`, or `{"code": "<contract_error_code>", "message": "..."}`. The codes are `unexpected_file_name`, `invalid_business_date`, `invalid_header`, `no_input_files`, `invalid_argument`. |
| `files` | Sorted by `business_date`, `revision`, `source_file`. Base names only. |
| `reject_reasons` | Lists **every** code from the data model, including those with a count of 0, so the keys are the same on every run. |
| `reject_rate` | A decimal string rounded half-up to 4 places. It is for display only; the gate compares exact values. |
| `gate.status` | `passed`, `failed`, or `not_evaluated` (after a contract error). |
| `reconciliation.status` | `passed`, `failed`, or `not_evaluated`. |
| `outputs_published` | `true` only when exit code is 0. |

Decimals are written as strings to avoid binary floating-point rounding in JSON.
