from datetime import date
from decimal import Decimal

import duckdb
import pytest

from orders_pipeline import ingest, transform

from conftest import make_row, write_csv


def validate(tmp_path, rows, name="orders_2026-09-01_r1.csv"):
    write_csv(tmp_path / "in", name, rows)
    con = duckdb.connect()
    ingest.load_raw_rows(con, ingest.discover_files(tmp_path / "in"))
    transform.run_steps(con, upto="10")
    return con


def reasons(con):
    return [r[0] for r in con.execute(
        "SELECT reject_reason FROM std_rows ORDER BY line_number").fetchall()]


def test_valid_row_is_typed(tmp_path):
    con = validate(tmp_path, [make_row()])
    row = con.execute(
        "SELECT reject_reason, order_date, quantity, unit_price FROM std_rows").fetchone()
    assert row == (None, date(2026, 9, 1), 2, Decimal("10.00"))
    types = dict(con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'std_rows'").fetchall())
    assert types["order_date"] == "DATE"
    assert types["quantity"] == "INTEGER"
    assert types["unit_price"] == "DECIMAL(12,2)"


@pytest.mark.parametrize("overrides, code", [
    ({"order_id": ""}, "missing_order_id"),
    ({"order_id": "   "}, "missing_order_id"),
    ({"customer_id": ""}, "missing_customer_id"),
    ({"product_id": ""}, "missing_product_id"),
    ({"order_date": "2026-13-45"}, "invalid_order_date"),
    ({"order_date": "02/09/2026"}, "invalid_order_date"),
    ({"order_date": "2026-9-1"}, "invalid_order_date"),
    ({"order_date": "2026-09-01T00:00"}, "invalid_order_date"),
    ({"order_date": "2026-09-02"}, "future_order_date"),
    ({"quantity": "0"}, "invalid_quantity"),
    ({"quantity": "-2"}, "invalid_quantity"),
    ({"quantity": "two"}, "invalid_quantity"),
    ({"quantity": "1.5"}, "invalid_quantity"),
    ({"quantity": "99999999999"}, "invalid_quantity"),
    ({"unit_price": "-9.99"}, "invalid_unit_price"),
    ({"unit_price": "0"}, "invalid_unit_price"),
    ({"unit_price": "0.00"}, "invalid_unit_price"),
    ({"unit_price": "1e3"}, "invalid_unit_price"),
    ({"unit_price": ".5"}, "invalid_unit_price"),
    ({"unit_price": "1,000.00"}, "invalid_unit_price"),
    ({"unit_price": "9.999"}, "invalid_unit_price"),
    ({"unit_price": "123456789012.00"}, "invalid_unit_price"),
    ({"category": "toys"}, "invalid_category"),
    ({"category": ""}, "invalid_category"),
    ({"status": "shipped"}, "invalid_status"),
    ({"status": ""}, "invalid_status"),
])
def test_reason_codes(tmp_path, overrides, code):
    con = validate(tmp_path, [make_row(**overrides)])
    assert reasons(con) == [code]


def test_malformed_row(tmp_path):
    con = validate(tmp_path, [make_row() + ["x"], make_row()[:5]])
    assert reasons(con) == ["malformed_row", "malformed_row"]


def test_precedence_first_failing_rule_wins(tmp_path):
    con = validate(tmp_path, [make_row(order_id="", quantity="two")])
    assert reasons(con) == ["missing_order_id"]


def test_future_is_relative_to_business_date_not_today(tmp_path):
    con = validate(tmp_path, [
        make_row(order_id="A", order_date="2026-09-02"),
        make_row(order_id="B", order_date="2026-08-31"),
        make_row(order_id="C", order_date="2026-09-01"),
    ])
    assert reasons(con) == ["future_order_date", None, None]


def test_standardisation(tmp_path):
    con = validate(tmp_path, [
        make_row(order_id="A", category=" Electronics "),
        make_row(order_id="B", status="Completed"),
        make_row(order_id="C", category="HOME", customer_id="  C1 "),
    ])
    rows = con.execute(
        "SELECT order_id, customer_id, category, status, reject_reason "
        "FROM std_rows ORDER BY line_number").fetchall()
    assert rows == [
        ("A", "C1", "electronics", "completed", None),
        ("B", "C1", "home", "completed", None),
        ("C", "C1", "home", "completed", None),
    ]
