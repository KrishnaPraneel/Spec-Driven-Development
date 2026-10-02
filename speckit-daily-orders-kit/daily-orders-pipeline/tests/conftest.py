import csv
import json
import shutil
from pathlib import Path

import duckdb
import pytest

from orders_pipeline import cli

EXPECTED_HEADER = [
    "order_id", "customer_id", "order_date", "product_id",
    "category", "quantity", "unit_price", "status",
]
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "incoming"
PUBLISHED = ["clean_orders", "rejected_orders", "daily_sales_summary"]


def write_csv(directory, name, rows=(), header=EXPECTED_HEADER, raw_text=None):
    """Write a fixture CSV. `raw_text` is written verbatim when given."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if raw_text is not None:
        path.write_text(raw_text, encoding="utf-8")
        return path
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
    return path


def run_cli(*args):
    return cli.main([str(a) for a in args])


def read_table(output_dir, name):
    path = Path(output_dir) / f"{name}.parquet"
    return duckdb.sql(f"SELECT * FROM '{path}'").fetchall()


def read_columns(output_dir, name):
    path = Path(output_dir) / f"{name}.parquet"
    return [d[0] for d in duckdb.sql(f"SELECT * FROM '{path}'").description]


def read_db_table(output_dir, name):
    con = duckdb.connect(str(Path(output_dir) / "orders.duckdb"), read_only=True)
    try:
        return con.execute(f"SELECT * FROM {name}").fetchall()
    finally:
        con.close()


def read_report(output_dir):
    return json.loads((Path(output_dir) / "run_report.json").read_text(encoding="utf-8"))


def make_row(**overrides):
    row = {
        "order_id": "ORD-1", "customer_id": "C1", "order_date": "2026-09-01",
        "product_id": "P1", "category": "home", "quantity": "2",
        "unit_price": "10.00", "status": "completed",
    }
    row.update(overrides)
    return [row[c] for c in EXPECTED_HEADER]


@pytest.fixture
def valid_row():
    return make_row


@pytest.fixture
def sample_input(tmp_path):
    target = tmp_path / "in"
    target.mkdir()
    for f in sorted(SAMPLE_DIR.glob("orders_*.csv")):
        shutil.copyfile(f, target / f.name)
    return target
