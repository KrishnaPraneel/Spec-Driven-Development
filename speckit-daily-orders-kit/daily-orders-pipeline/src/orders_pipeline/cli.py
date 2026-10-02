"""Command-line entry point: python -m orders_pipeline --input DIR --output DIR.

Exit codes: 0 success, 1 data failure (gate or reconciliation), 2 contract/usage error.
"""

import argparse
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb

from orders_pipeline import ingest, publish, report, transform
from orders_pipeline.ingest import ContractError


class RunLog:
    """Plain-text log, one line per event, to stderr and <output>/pipeline.log."""

    def __init__(self):
        self._fh = None

    def open(self, output_dir):
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            self._fh = open(Path(output_dir) / "pipeline.log", "w", encoding="utf-8")
        except OSError:
            self._fh = None

    def __call__(self, event, level="INFO", **kv):
        # The timestamp is diagnostic only; the log is not a data output.
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        fields = " ".join(f"{k}={kv[k]}" for k in sorted(kv))
        line = f"{stamp} {level} {event}" + (f" {fields}" if fields else "")
        print(line, file=sys.stderr)
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None


def parse_threshold(text):
    try:
        value = Decimal(text)
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or not (0 <= value <= 1):
        raise ContractError(
            "invalid_argument", "--max-reject-rate must be a decimal from 0 to 1"
        )
    return value


def build_parser():
    parser = argparse.ArgumentParser(prog="orders_pipeline")
    parser.add_argument("--input", required=True, help="folder with orders_<date>_r<N>.csv files")
    parser.add_argument("--output", required=True, help="folder for outputs")
    parser.add_argument("--max-reject-rate", default="0.10",
                        help="fail when the reject rate is strictly greater (default 0.10)")
    return parser


def _collect(con):
    files = [
        {"source_file": f, "business_date": d.isoformat(), "revision": r,
         "rows": n, "blank_lines": b}
        for f, d, r, n, b in con.execute(
            "SELECT source_file, business_date, revision, row_count, blank_lines "
            "FROM input_files ORDER BY business_date, revision, source_file").fetchall()
    ]
    by_outcome = dict(con.execute(
        "SELECT outcome, count(*) FROM row_outcomes GROUP BY outcome").fetchall())
    counts = {
        "rows_read": con.execute("SELECT count(*) FROM raw_rows").fetchone()[0],
        "rows_clean": by_outcome.get("clean", 0),
        "rows_rejected": by_outcome.get("rejected", 0),
        "rows_superseded": by_outcome.get("superseded", 0),
        "superseded_by_reason": dict(con.execute(
            "SELECT reason, count(*) FROM row_outcomes WHERE outcome = 'superseded' "
            "GROUP BY reason").fetchall()),
    }
    reject_reasons = dict(con.execute(
        "SELECT reason, count(*) FROM row_outcomes WHERE outcome = 'rejected' "
        "GROUP BY reason").fetchall())
    result = con.execute("SELECT * FROM reconciliation")
    names = [d[0] for d in result.description]
    checks = {n: bool(v) for n, v in zip(names, result.fetchone())}
    return files, counts, reject_reasons, checks


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2

    output = Path(args.output)
    log = RunLog()
    log.open(output)
    log("run_started")

    state = {
        "status": "failed", "error": None, "files": [], "counts": None,
        "reject_reasons": None, "outputs_published": False,
        "gate": {"reject_rate": None, "threshold": args.max_reject_rate,
                 "status": "not_evaluated"},
        "reconciliation": {"status": "not_evaluated", "checks": {}},
    }
    exit_code = 2
    try:
        threshold = parse_threshold(args.max_reject_rate)
        files = ingest.discover_files(args.input)
        log("files_discovered", count=len(files))
        con = duckdb.connect()
        ingest.load_raw_rows(con, files, log=log)
        transform.run_steps(con, log=log)

        state["files"], counts, reasons, checks = _collect(con)
        state["counts"], state["reject_reasons"] = counts, reasons

        recon_ok = all(checks.values())
        state["reconciliation"] = {"status": "passed" if recon_ok else "failed",
                                   "checks": checks}
        log("reconciliation_checked", status=state["reconciliation"]["status"])

        rate, gate_ok = publish.evaluate_gate(
            counts["rows_rejected"], counts["rows_read"], threshold)
        state["gate"] = {"reject_rate": report.format_rate(rate),
                         "threshold": args.max_reject_rate,
                         "status": "passed" if gate_ok else "failed"}
        log("gate_evaluated", reject_rate=state["gate"]["reject_rate"],
            threshold=args.max_reject_rate, status=state["gate"]["status"])

        if recon_ok and gate_ok:
            publish.publish(con, output)
            state["outputs_published"] = True
            state["status"] = "succeeded"
            log("outputs_published", tables=",".join(publish.PUBLISHED_TABLES))
            exit_code = 0
        else:
            log("outputs_withheld", level="WARNING")
            exit_code = 1
    except ContractError as exc:
        state["error"] = {"code": exc.code, "message": exc.message}
        log("contract_error", level="ERROR", code=exc.code)
        exit_code = 2
    finally:
        try:
            report.write_report(output / "run_report.json", report.build_report(
                status=state["status"], error=state["error"],
                max_reject_rate=args.max_reject_rate, files=state["files"],
                counts=state["counts"], reject_reasons=state["reject_reasons"],
                gate=state["gate"], reconciliation=state["reconciliation"],
                outputs_published=state["outputs_published"]))
        except OSError:
            log("report_not_written", level="ERROR")
        log("run_finished", exit_code=exit_code)
        log.close()
    return exit_code
