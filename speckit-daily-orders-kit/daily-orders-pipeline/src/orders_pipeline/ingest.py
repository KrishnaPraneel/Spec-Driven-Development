"""File discovery, the input file contract, and loading raw rows into DuckDB.

Every value is kept as the original string. All validation happens later, in SQL.
"""

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

EXPECTED_HEADER = [
    "order_id", "customer_id", "order_date", "product_id",
    "category", "quantity", "unit_price", "status",
]
FILE_PATTERN = re.compile(r"^orders_(\d{4}-\d{2}-\d{2})_r([1-9][0-9]*)\.csv$")


class ContractError(Exception):
    """An input-contract or usage violation that fails the whole run (exit code 2)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class InputFile:
    source_file: str
    path: Path
    business_date: date
    revision: int


def discover_files(input_dir):
    """Return the input files sorted by (business_date, revision, name)."""
    directory = Path(input_dir)
    if not directory.is_dir():
        raise ContractError("invalid_argument", "input folder does not exist")
    files = []
    for path in directory.iterdir():
        if path.name.startswith(".") or path.is_dir():
            continue
        match = FILE_PATTERN.match(path.name)
        if not match:
            raise ContractError("unexpected_file_name", f"unexpected file name: {path.name}")
        try:
            business_date = date.fromisoformat(match[1])
        except ValueError:
            raise ContractError(
                "invalid_business_date", f"invalid business date in file name: {path.name}"
            ) from None
        files.append(InputFile(path.name, path, business_date, int(match[2])))
    if not files:
        raise ContractError("no_input_files", "no input files found")
    return sorted(files, key=lambda f: (f.business_date, f.revision, f.source_file))


def _read_file(f):
    records = []
    blank_lines = 0
    with open(f.path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header != EXPECTED_HEADER:
            raise ContractError(
                "invalid_header",
                f"{f.source_file}: header must be exactly {','.join(EXPECTED_HEADER)}",
            )
        for record in reader:
            if not record:
                blank_lines += 1
                continue
            values = record[:8] + [None] * (8 - len(record))
            extra = ",".join(record[8:]) if len(record) > 8 else None
            records.append((
                f"{f.source_file}:{reader.line_num}", f.source_file, reader.line_num,
                f.business_date, f.revision, len(record), *values, extra,
            ))
    return records, blank_lines


def load_raw_rows(con, files, log=None):
    """Create `input_files` and `raw_rows` and fill them from the given files."""
    con.execute("""
        CREATE OR REPLACE TABLE input_files (
            source_file VARCHAR, entity VARCHAR, business_date DATE, revision INTEGER,
            row_count INTEGER, blank_lines INTEGER
        )""")
    con.execute("""
        CREATE OR REPLACE TABLE raw_rows (
            row_id VARCHAR PRIMARY KEY, source_file VARCHAR, line_number INTEGER,
            business_date DATE, revision INTEGER, field_count INTEGER,
            order_id VARCHAR, customer_id VARCHAR, order_date VARCHAR, product_id VARCHAR,
            category VARCHAR, quantity VARCHAR, unit_price VARCHAR, status VARCHAR,
            extra_values VARCHAR
        )""")
    for f in files:
        records, blank_lines = _read_file(f)
        con.execute(
            "INSERT INTO input_files VALUES (?, 'orders', ?, ?, ?, ?)",
            [f.source_file, f.business_date, f.revision, len(records), blank_lines],
        )
        if records:
            con.executemany(
                "INSERT INTO raw_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                records,
            )
        if log:
            log("file_read", file=f.source_file, rows=len(records), blank_lines=blank_lines)
