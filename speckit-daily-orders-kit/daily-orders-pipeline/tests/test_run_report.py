import json
import re

from conftest import make_row, read_report, run_cli, write_csv

CODES = ["malformed_row", "missing_order_id", "missing_customer_id", "missing_product_id",
         "invalid_order_date", "future_order_date", "invalid_quantity", "invalid_unit_price",
         "invalid_category", "invalid_status", "conflicting_order_id"]
TOP_KEYS = {"status", "error", "config", "files", "counts", "reject_reasons", "gate",
            "reconciliation", "outputs_published"}


def run(tmp_path, *extra):
    write_csv(tmp_path / "in", "orders_2026-09-02_r1.csv",
              [make_row(order_id="B", order_date="2026-09-02"),
               make_row(order_id="B", order_date="2026-09-02")])
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv",
              [make_row(order_id="A"), make_row(order_id="X", quantity="0"),
               make_row(order_id="Y", quantity="x")])
    out = tmp_path / "out"
    code = run_cli("--input", tmp_path / "in", "--output", out, *extra)
    return code, out


def test_shape_and_values(tmp_path):
    code, out = run(tmp_path, "--max-reject-rate", "1")
    assert code == 0
    r = read_report(out)
    assert set(r) == TOP_KEYS
    assert r["status"] == "succeeded" and r["error"] is None and r["outputs_published"] is True
    assert r["config"] == {"max_reject_rate": "1"}
    assert list(r["reject_reasons"]) == sorted(CODES)
    assert r["reject_reasons"]["invalid_quantity"] == 2
    assert sum(r["reject_reasons"].values()) == r["counts"]["rows_rejected"] == 2
    c = r["counts"]
    assert c == {"rows_read": 5, "rows_clean": 2, "rows_rejected": 2, "rows_superseded": 1,
                 "superseded_by_reason": {"exact_duplicate": 1, "older_revision": 0}}
    assert c["rows_read"] == c["rows_clean"] + c["rows_rejected"] + c["rows_superseded"]
    assert r["gate"] == {"reject_rate": "0.4000", "threshold": "1", "status": "passed"}
    assert r["reconciliation"]["status"] == "passed"
    assert all(v is True for v in r["reconciliation"]["checks"].values())
    assert set(r["reconciliation"]["checks"]) == {
        "counts_balance", "row_ids_unique", "clean_order_id_unique", "clean_count_match",
        "reasons_sum", "summary_orders_match"}
    assert [f["source_file"] for f in r["files"]] == [
        "orders_2026-09-01_r1.csv", "orders_2026-09-02_r1.csv"]
    assert r["files"][0] == {"source_file": "orders_2026-09-01_r1.csv",
                             "business_date": "2026-09-01", "revision": 1,
                             "rows": 3, "blank_lines": 0}


def test_formatting_and_no_absolute_paths(tmp_path):
    _, out = run(tmp_path)
    text = (out / "run_report.json").read_text(encoding="utf-8")
    report = json.loads(text)
    assert text == json.dumps(report, sort_keys=True, indent=2) + "\n"
    assert str(tmp_path) not in text
    assert isinstance(report["gate"]["reject_rate"], str)
    assert report["config"]["max_reject_rate"] == "0.10"


def test_reject_rate_rounds_half_up(tmp_path):
    rows = [make_row(order_id=f"O{i}", quantity="0" if i < 1 else "1") for i in range(16)]
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv", rows)   # 1/16 = 0.0625
    run_cli("--input", tmp_path / "in", "--output", tmp_path / "out", "--max-reject-rate", "1")
    assert read_report(tmp_path / "out")["gate"]["reject_rate"] == "0.0625"
    rows = [make_row(order_id=f"O{i}", quantity="0" if i < 1 else "1") for i in range(32)]
    write_csv(tmp_path / "in2", "orders_2026-09-01_r1.csv", rows)  # 1/32 = 0.03125
    run_cli("--input", tmp_path / "in2", "--output", tmp_path / "out2", "--max-reject-rate", "1")
    assert read_report(tmp_path / "out2")["gate"]["reject_rate"] == "0.0313"


def test_contract_error_report(tmp_path):
    write_csv(tmp_path / "in", "orders_latest.csv", [make_row()])
    out = tmp_path / "out"
    assert run_cli("--input", tmp_path / "in", "--output", out) == 2
    r = read_report(out)
    assert set(r) == TOP_KEYS
    assert r["status"] == "failed"
    assert r["error"]["code"] == "unexpected_file_name"
    assert r["gate"]["status"] == "not_evaluated"
    assert r["reconciliation"]["status"] == "not_evaluated"
    assert r["outputs_published"] is False
    assert list(r["reject_reasons"]) == sorted(CODES)


def test_log_is_plain_text_one_line_per_event(tmp_path):
    _, out = run(tmp_path, "--max-reject-rate", "1")
    lines = (out / "pipeline.log").read_text(encoding="utf-8").splitlines()
    pattern = re.compile(r"^\S+ (INFO|WARNING|ERROR) [a-z_]+( [a-z_]+=\S+)*$")
    assert lines and all(pattern.match(line) for line in lines), lines
    events = [line.split()[2] for line in lines]
    assert events[0] == "run_started" and events[-1] == "run_finished"
    for e in ["files_discovered", "file_read", "step_done", "gate_evaluated",
              "reconciliation_checked", "outputs_published"]:
        assert e in events
    # Overwritten each run, not appended.
    run(tmp_path, "--max-reject-rate", "1")
    assert (out / "pipeline.log").read_text(encoding="utf-8").count("run_started") == 1
