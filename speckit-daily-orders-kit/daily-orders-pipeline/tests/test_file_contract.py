import os
from datetime import date

import duckdb
import pytest

from orders_pipeline import ingest
from orders_pipeline.ingest import ContractError

from conftest import EXPECTED_HEADER, make_row, run_cli, write_csv


@pytest.mark.parametrize("name", [
    "orders_latest.csv",
    "orders_2026-09-01.csv",
    "orders_2026-09-01_r0.csv",
    "orders_2026-09-01_r01.csv",
    "Orders_2026-09-01_r1.csv",
    "orders_2026-09-01_r1.txt",
])
def test_unexpected_file_name(tmp_path, name):
    write_csv(tmp_path / "in", name, [make_row()])
    with pytest.raises(ContractError) as exc:
        ingest.discover_files(tmp_path / "in")
    assert exc.value.code == "unexpected_file_name"
    assert run_cli("--input", tmp_path / "in", "--output", tmp_path / "out") == 2


def test_invalid_business_date(tmp_path):
    write_csv(tmp_path / "in", "orders_2026-02-30_r1.csv", [make_row()])
    with pytest.raises(ContractError) as exc:
        ingest.discover_files(tmp_path / "in")
    assert exc.value.code == "invalid_business_date"


@pytest.mark.parametrize("header", [
    EXPECTED_HEADER[:-1],
    EXPECTED_HEADER + ["extra"],
    ["order_no"] + EXPECTED_HEADER[1:],
    [EXPECTED_HEADER[1], EXPECTED_HEADER[0]] + EXPECTED_HEADER[2:],
])
def test_invalid_header(tmp_path, header):
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv", [], header=header)
    files = ingest.discover_files(tmp_path / "in")
    with pytest.raises(ContractError) as exc:
        ingest.load_raw_rows(duckdb.connect(), files)
    assert exc.value.code == "invalid_header"
    assert run_cli("--input", tmp_path / "in", "--output", tmp_path / "out") == 2


def test_empty_folder(tmp_path):
    (tmp_path / "in").mkdir()
    with pytest.raises(ContractError) as exc:
        ingest.discover_files(tmp_path / "in")
    assert exc.value.code == "no_input_files"
    assert run_cli("--input", tmp_path / "in", "--output", tmp_path / "out") == 2


def test_missing_input_folder(tmp_path):
    with pytest.raises(ContractError) as exc:
        ingest.discover_files(tmp_path / "nope")
    assert exc.value.code == "invalid_argument"
    assert run_cli("--input", tmp_path / "nope", "--output", tmp_path / "out") == 2


def test_hidden_files_and_subfolders_ignored(tmp_path):
    d = tmp_path / "in"
    write_csv(d, "orders_2026-09-01_r1.csv", [make_row()])
    (d / ".DS_Store").write_bytes(b"\x00")
    (d / "archive").mkdir()
    files = ingest.discover_files(d)
    assert [f.source_file for f in files] == ["orders_2026-09-01_r1.csv"]


def test_header_only_file_accepted(tmp_path):
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv", [])
    con = duckdb.connect()
    ingest.load_raw_rows(con, ingest.discover_files(tmp_path / "in"))
    assert con.execute("SELECT count(*) FROM raw_rows").fetchone()[0] == 0
    assert con.execute("SELECT row_count FROM input_files").fetchone()[0] == 0


def test_bom_tolerated(tmp_path):
    text = "﻿" + ",".join(EXPECTED_HEADER) + "\n" + ",".join(make_row()) + "\n"
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv", raw_text=text)
    con = duckdb.connect()
    ingest.load_raw_rows(con, ingest.discover_files(tmp_path / "in"))
    assert con.execute("SELECT order_id FROM raw_rows").fetchone()[0] == "ORD-1"


def test_blank_lines_skipped_and_counted(tmp_path):
    text = (",".join(EXPECTED_HEADER) + "\n"
            + ",".join(make_row(order_id="A")) + "\n"
            + "\n"
            + ",".join(make_row(order_id="B")) + "\n")
    write_csv(tmp_path / "in", "orders_2026-09-01_r1.csv", raw_text=text)
    con = duckdb.connect()
    ingest.load_raw_rows(con, ingest.discover_files(tmp_path / "in"))
    rows = con.execute("SELECT order_id, line_number FROM raw_rows ORDER BY line_number").fetchall()
    assert rows == [("A", 2), ("B", 4)]
    assert con.execute("SELECT row_count, blank_lines FROM input_files").fetchone() == (2, 1)


def test_sort_order_numeric_revision_and_not_mtime(tmp_path):
    d = tmp_path / "in"
    names = ["orders_2026-09-02_r1.csv", "orders_2026-09-01_r10.csv",
             "orders_2026-09-01_r2.csv", "orders_2026-09-01_r1.csv"]
    for i, n in enumerate(names):
        p = write_csv(d, n, [make_row()])
        os.utime(p, (1_000_000 + i * 1000, 1_000_000 + i * 1000))
    files = ingest.discover_files(d)
    assert [f.source_file for f in files] == [
        "orders_2026-09-01_r1.csv", "orders_2026-09-01_r2.csv",
        "orders_2026-09-01_r10.csv", "orders_2026-09-02_r1.csv",
    ]
    assert files[2].revision == 10
    assert files[0].business_date == date(2026, 9, 1)
