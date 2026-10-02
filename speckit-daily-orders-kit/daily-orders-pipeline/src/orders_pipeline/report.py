"""Builds and writes run_report.json (contracts/run-report.md).

The report has no timestamps and no absolute paths, and its keys are sorted, so the
same input and configuration give a byte-identical report.
"""

import json
from decimal import ROUND_HALF_UP, Decimal

REJECT_CODES = [
    "malformed_row", "missing_order_id", "missing_customer_id", "missing_product_id",
    "invalid_order_date", "future_order_date", "invalid_quantity", "invalid_unit_price",
    "invalid_category", "invalid_status", "conflicting_order_id",
]
SUPERSEDED_REASONS = ["exact_duplicate", "older_revision"]


def format_rate(rate):
    return str(Decimal(rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def build_report(*, status, error, max_reject_rate, files, counts, reject_reasons,
                 gate, reconciliation, outputs_published):
    counts = counts or {}
    return {
        "status": status,
        "error": error,
        "config": {"max_reject_rate": max_reject_rate},
        "files": files,
        "counts": {
            "rows_read": counts.get("rows_read", 0),
            "rows_clean": counts.get("rows_clean", 0),
            "rows_rejected": counts.get("rows_rejected", 0),
            "rows_superseded": counts.get("rows_superseded", 0),
            "superseded_by_reason": {
                r: counts.get("superseded_by_reason", {}).get(r, 0) for r in SUPERSEDED_REASONS
            },
        },
        "reject_reasons": {code: (reject_reasons or {}).get(code, 0) for code in REJECT_CODES},
        "gate": gate,
        "reconciliation": reconciliation,
        "outputs_published": outputs_published,
    }


def write_report(path, report):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
