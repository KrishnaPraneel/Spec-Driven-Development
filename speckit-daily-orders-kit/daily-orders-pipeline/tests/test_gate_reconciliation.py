import pytest

from orders_pipeline import transform

from conftest import make_row, read_report, run_cli, write_csv

F1 = "orders_2026-09-01_r1.csv"
OUTPUT_FILES = ["clean_orders.parquet", "rejected_orders.parquet",
                "daily_sales_summary.parquet", "orders.duckdb"]


def batch(tmp_path, n_rows, n_bad, folder="in"):
    rows = [make_row(order_id=f"ORD-{i}", quantity="0" if i < n_bad else "1")
            for i in range(n_rows)]
    write_csv(tmp_path / folder, F1, rows)
    return tmp_path / folder


def snapshot(out):
    return {name: ((out / name).read_bytes(), (out / name).stat().st_mtime_ns)
            for name in OUTPUT_FILES}


def test_gate_fails_above_threshold_and_publishes_nothing(tmp_path):
    src = batch(tmp_path, 10, 2)
    out = tmp_path / "out"
    assert run_cli("--input", src, "--output", out) == 1
    for name in OUTPUT_FILES:
        assert not (out / name).exists()
    report = read_report(out)
    assert report["gate"]["status"] == "failed"
    assert report["outputs_published"] is False
    assert report["status"] == "failed"


def test_exactly_ten_percent_passes(tmp_path):
    src = batch(tmp_path, 10, 1)
    assert run_cli("--input", src, "--output", tmp_path / "out", "--max-reject-rate", "0.10") == 0
    assert read_report(tmp_path / "out")["gate"]["status"] == "passed"


def test_custom_threshold(tmp_path):
    src = batch(tmp_path, 10, 1)
    assert run_cli("--input", src, "--output", tmp_path / "out", "--max-reject-rate", "0.05") == 1


def test_failed_run_leaves_earlier_outputs_untouched(tmp_path):
    good = batch(tmp_path, 10, 0, folder="good")
    bad = batch(tmp_path, 10, 5, folder="bad")
    out = tmp_path / "out"
    assert run_cli("--input", good, "--output", out) == 0
    before = snapshot(out)
    assert run_cli("--input", bad, "--output", out) == 1
    assert snapshot(out) == before


@pytest.mark.parametrize("value", ["1.5", "-0.1", "abc", "nan"])
def test_invalid_threshold(tmp_path, value):
    src = batch(tmp_path, 3, 0)
    out = tmp_path / "out"
    assert run_cli("--input", src, "--output", out, "--max-reject-rate", value) == 2
    assert read_report(out)["error"]["code"] == "invalid_argument"


def test_reconciliation_failure_blocks_publish(tmp_path, monkeypatch):
    original = transform.run_steps

    def broken(con, **kwargs):
        # Lose one row after the outputs are built, then run the checks (step 70).
        original(con, upto="62", log=kwargs.get("log"))
        con.execute("DELETE FROM row_outcomes WHERE row_id = (SELECT min(row_id) FROM row_outcomes)")
        original(con, start="70", log=kwargs.get("log"))

    monkeypatch.setattr(transform, "run_steps", broken)
    src = batch(tmp_path, 5, 0)
    out = tmp_path / "out"
    assert run_cli("--input", src, "--output", out) == 1
    report = read_report(out)
    assert report["reconciliation"]["status"] == "failed"
    assert report["reconciliation"]["checks"]["counts_balance"] is False
    assert report["outputs_published"] is False
    for name in OUTPUT_FILES:
        assert not (out / name).exists()


def test_no_staging_left_behind(tmp_path):
    out = tmp_path / "out"
    run_cli("--input", batch(tmp_path, 5, 0, "a"), "--output", out)
    run_cli("--input", batch(tmp_path, 5, 5, "b"), "--output", out)
    assert not (out / ".staging").exists()
