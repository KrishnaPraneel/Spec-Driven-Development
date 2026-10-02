import os
import shutil

import duckdb

from conftest import PUBLISHED, SAMPLE_DIR, read_db_table, read_table, run_cli


def outputs(out):
    return {
        "parquet": {t: read_table(out, t) for t in PUBLISHED},
        "db": {t: read_db_table(out, t) for t in PUBLISHED},
        "report": (out / "run_report.json").read_bytes(),
    }


def test_rerun_gives_identical_outputs(sample_input, tmp_path):
    out = tmp_path / "out"
    assert run_cli("--input", sample_input, "--output", out) == 0
    first = outputs(out)
    assert run_cli("--input", sample_input, "--output", out) == 0
    assert outputs(out) == first


def test_independent_of_file_arrival_order_and_mtime(sample_input, tmp_path):
    other = tmp_path / "in2"
    other.mkdir()
    for i, f in enumerate(sorted(SAMPLE_DIR.glob("orders_*.csv"), reverse=True)):
        shutil.copyfile(f, other / f.name)
        os.utime(other / f.name, (2_000_000 - i * 5000, 2_000_000 - i * 5000))
    assert run_cli("--input", sample_input, "--output", tmp_path / "a") == 0
    assert run_cli("--input", other, "--output", tmp_path / "b") == 0
    assert outputs(tmp_path / "a") == outputs(tmp_path / "b")


def test_no_dependency_on_previous_outputs(sample_input, tmp_path):
    out = tmp_path / "out"
    assert run_cli("--input", sample_input, "--output", tmp_path / "fresh") == 0
    out.mkdir()
    con = duckdb.connect(str(out / "orders.duckdb"))
    con.execute("CREATE TABLE junk AS SELECT 1 AS x")
    con.execute("CREATE TABLE clean_orders AS SELECT 'stale' AS order_id")
    con.close()
    duckdb.sql(f"COPY (SELECT 42 AS x) TO '{out / 'clean_orders.parquet'}' (FORMAT parquet)")
    assert run_cli("--input", sample_input, "--output", out) == 0
    assert outputs(out) == outputs(tmp_path / "fresh")
    con = duckdb.connect(str(out / "orders.duckdb"), read_only=True)
    tables = sorted(r[0] for r in con.execute("SHOW TABLES").fetchall())
    con.close()
    assert tables == sorted(PUBLISHED)
