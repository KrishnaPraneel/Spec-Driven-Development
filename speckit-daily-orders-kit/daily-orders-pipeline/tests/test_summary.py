from datetime import date
from decimal import Decimal

from conftest import make_row, read_columns, read_table, run_cli, write_csv

F1 = "orders_2026-09-01_r1.csv"
F1R2 = "orders_2026-09-01_r2.csv"


def run(tmp_path, files):
    for name, rows in files.items():
        write_csv(tmp_path / "in", name, rows)
    out = tmp_path / "out"
    assert run_cli("--input", tmp_path / "in", "--output", out, "--max-reject-rate", "1") == 0
    return read_table(out, "daily_sales_summary"), out


def test_columns(tmp_path):
    _, out = run(tmp_path, {F1: [make_row()]})
    assert read_columns(out, "daily_sales_summary") == [
        "order_date", "category", "orders", "units", "revenue"]


def test_grouping_completed_only_and_exact_decimals(tmp_path):
    rows, _ = run(tmp_path, {F1: [
        make_row(order_id="A", quantity="1", unit_price="0.10"),
        make_row(order_id="B", quantity="2", unit_price="0.10"),
        make_row(order_id="C", quantity="1", unit_price="0.20"),
        make_row(order_id="D", quantity="5", unit_price="9.99", status="cancelled"),
        make_row(order_id="E", quantity="1", unit_price="4.00", category="grocery",
                 status="cancelled"),
        make_row(order_id="F", quantity="1", unit_price="3.00", category="apparel",
                 order_date="2026-08-31"),
        make_row(order_id="G", quantity="0"),  # rejected: contributes nothing
    ]})
    assert rows == [
        (date(2026, 8, 31), "apparel", 1, 1, Decimal("3.00")),
        (date(2026, 9, 1), "home", 3, 4, Decimal("0.50")),
    ]
    assert isinstance(rows[1][4], Decimal)


def test_revised_order_uses_latest_values_and_duplicates_count_once(tmp_path):
    rows, _ = run(tmp_path, {
        F1: [make_row(order_id="A", quantity="1"), make_row(order_id="A", quantity="1")],
        F1R2: [make_row(order_id="A", quantity="3")],
    })
    assert rows == [(date(2026, 9, 1), "home", 1, 3, Decimal("30.00"))]


def test_sorted_by_date_then_category(tmp_path):
    rows, _ = run(tmp_path, {F1: [
        make_row(order_id="A", category="home"),
        make_row(order_id="B", category="apparel"),
        make_row(order_id="C", category="grocery", order_date="2026-08-30"),
    ]})
    assert [(r[0], r[1]) for r in rows] == sorted((r[0], r[1]) for r in rows)
