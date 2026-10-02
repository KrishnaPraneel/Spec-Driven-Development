"""Writing the published tables as Parquet files and into one DuckDB database file."""

import os
import shutil
from decimal import Decimal
from pathlib import Path

# Published table -> the documented sort key used for every write (constitution I).
PUBLISHED_TABLES = {
    "clean_orders": "order_id",
    "rejected_orders": "source_file, line_number",
    "daily_sales_summary": "order_date, category",
}
DB_FILE = "orders.duckdb"
STAGING_DIR = ".staging"


def _sql_path(path):
    return str(path).replace("'", "''")


def write_outputs(con, target_dir):
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for table, key in PUBLISHED_TABLES.items():
        path = _sql_path(target / f"{table}.parquet")
        con.execute(f"COPY (SELECT * FROM {table} ORDER BY {key}) TO '{path}' (FORMAT parquet)")
    db_path = target / DB_FILE
    if db_path.exists():
        db_path.unlink()
    con.execute(f"ATTACH '{_sql_path(db_path)}' AS out")
    try:
        for table, key in PUBLISHED_TABLES.items():
            con.execute(f"CREATE TABLE out.{table} AS SELECT * FROM {table} ORDER BY {key}")
    finally:
        con.execute("DETACH out")


def evaluate_gate(rows_rejected, rows_read, threshold):
    """Return (reject_rate, passed). The run passes when the rate is <= threshold."""
    rate = Decimal(rows_rejected) / Decimal(rows_read) if rows_read else Decimal(0)
    return rate, rate <= threshold


def publish(con, output_dir):
    """Build every output in <output>/.staging, then move each file into place.

    Only called after the gate and reconciliation have passed, so a failed run never
    touches earlier outputs.
    """
    output = Path(output_dir)
    staging = output / STAGING_DIR
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        write_outputs(con, staging)
        for name in [f"{t}.parquet" for t in PUBLISHED_TABLES] + [DB_FILE]:
            os.replace(staging / name, output / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
