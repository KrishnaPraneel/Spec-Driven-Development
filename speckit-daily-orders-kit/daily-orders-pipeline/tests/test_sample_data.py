"""End-to-end checks on the 4 provided sample files (data/incoming)."""

import duckdb
import pytest

from conftest import read_columns, read_db_table, read_report, read_table, run_cli

R1 = "orders_2026-09-01_r1.csv"
R2 = "orders_2026-09-01_r2.csv"
D2 = "orders_2026-09-02_r1.csv"
D3 = "orders_2026-09-03_r1.csv"
PLANTED_REJECTS = sorted([
    (R1, 14, "invalid_quantity"),
    (R1, 22, "invalid_order_date"),
    (D2, 7, "missing_customer_id"),
    (D2, 12, "invalid_quantity"),
    (D2, 17, "invalid_unit_price"),
    (D2, 22, "invalid_order_date"),
    (D2, 27, "missing_order_id"),
    (D3, 10, "future_order_date"),
    (D3, 20, "invalid_quantity"),
])
REJECTED_ORDER_IDS = {"ORD-000013", "ORD-000021", "ORD-000106", "ORD-000111",
                      "ORD-000116", "ORD-000121", "ORD-000209", "ORD-000219"}


@pytest.fixture
def sample_run(sample_input, tmp_path):
    out = tmp_path / "out"
    code = run_cli("--input", sample_input, "--output", out, "--max-reject-rate", "0.10")
    return code, out


def clean_by_id(out):
    cols = read_columns(out, "clean_orders")
    return {r[0]: dict(zip(cols, r)) for r in read_table(out, "clean_orders")}


# --- US1: clean orders ------------------------------------------------------

def test_us1_clean_orders(sample_run):
    code, out = sample_run
    assert code == 0
    rows = read_table(out, "clean_orders")
    assert len(rows) == 124
    c = clean_by_id(out)
    assert len(c) == 124
    assert c["ORD-000003"]["quantity"] == 6 and c["ORD-000003"]["source_file"] == R2
    assert c["ORD-000016"]["status"] == "cancelled" and c["ORD-000016"]["source_file"] == R2
    assert all(f"ORD-0000{n}" in c for n in range(41, 49))
    assert "ORD-000136" in c
    assert not REJECTED_ORDER_IDS & c.keys()
    assert {r["category"] for r in c.values()} <= {"electronics", "home", "grocery", "apparel"}
    assert {r["status"] for r in c.values()} <= {"completed", "cancelled"}
    assert c["ORD-000026"]["category"] == "electronics"
    assert c["ORD-000031"]["status"] == "completed"
    assert c["ORD-000131"]["category"] == "home"
    assert c["ORD-000229"]["category"] == "apparel"
    ids = [r[0] for r in rows]
    assert ids == sorted(ids)
    assert read_db_table(out, "clean_orders") == rows


# --- US2: quarantine --------------------------------------------------------

def test_us2_rejected_orders(sample_run):
    code, out = sample_run
    assert code == 0
    rows = read_table(out, "rejected_orders")
    cols = read_columns(out, "rejected_orders")
    got = sorted((r[cols.index("source_file")], r[cols.index("line_number")],
                  r[cols.index("reject_reason")]) for r in rows)
    assert got == PLANTED_REJECTS
    assert read_db_table(out, "rejected_orders") == rows


# --- US3: daily sales summary -----------------------------------------------

def test_us3_daily_sales_summary(sample_run):
    code, out = sample_run
    assert code == 0
    rows = read_table(out, "daily_sales_summary")
    assert sum(r[2] for r in rows) == 116
    expected = duckdb.sql(f"""
        SELECT order_date, category, COUNT(*), SUM(quantity), SUM(line_revenue)
        FROM '{out / "clean_orders.parquet"}'
        WHERE status = 'completed'
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()
    assert rows == expected
    assert read_db_table(out, "daily_sales_summary") == rows


# --- US4: run report --------------------------------------------------------

def test_us4_run_report(sample_run):
    code, out = sample_run
    assert code == 0
    r = read_report(out)
    assert r["status"] == "succeeded"
    assert r["counts"] == {
        "rows_read": 138, "rows_clean": 124, "rows_rejected": 9, "rows_superseded": 5,
        "superseded_by_reason": {"exact_duplicate": 3, "older_revision": 2},
    }
    reasons = {k: v for k, v in r["reject_reasons"].items() if v}
    assert reasons == {"invalid_quantity": 3, "invalid_order_date": 2,
                       "missing_customer_id": 1, "missing_order_id": 1,
                       "invalid_unit_price": 1, "future_order_date": 1}
    assert r["gate"] == {"reject_rate": "0.0652", "threshold": "0.10", "status": "passed"}
    assert r["reconciliation"]["status"] == "passed"
    assert r["outputs_published"] is True
    assert [(f["source_file"], f["rows"]) for f in r["files"]] == [
        (R1, 42), (R2, 10), (D2, 45), (D3, 41)]
