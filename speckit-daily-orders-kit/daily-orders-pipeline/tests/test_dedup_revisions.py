import duckdb

from orders_pipeline import ingest, transform

from conftest import make_row, write_csv


def run(tmp_path, files):
    """files: {file name: [rows]}. Returns a connection after all SQL steps."""
    for name, rows in files.items():
        write_csv(tmp_path / "in", name, rows)
    con = duckdb.connect()
    ingest.load_raw_rows(con, ingest.discover_files(tmp_path / "in"))
    transform.run_steps(con)
    return con


def outcomes(con):
    return {r[0]: r[1:] for r in con.execute(
        "SELECT row_id, outcome, reason, superseded_by FROM row_outcomes").fetchall()}


def clean(con):
    return {r[0]: r[1:] for r in con.execute(
        "SELECT order_id, quantity, status, source_file, revision FROM clean_orders").fetchall()}


F1 = "orders_2026-09-01_r1.csv"
F1R2 = "orders_2026-09-01_r2.csv"
F2 = "orders_2026-09-02_r1.csv"


def assert_one_outcome_per_row(con):
    raw = con.execute("SELECT count(*) FROM raw_rows").fetchone()[0]
    distinct = con.execute("SELECT count(DISTINCT row_id) FROM row_outcomes").fetchone()[0]
    total = con.execute("SELECT count(*) FROM row_outcomes").fetchone()[0]
    missing = con.execute(
        "SELECT count(*) FROM raw_rows ANTI JOIN row_outcomes USING (row_id)").fetchone()[0]
    assert raw == distinct == total and missing == 0


def test_in_file_exact_duplicate(tmp_path):
    con = run(tmp_path, {F1: [make_row(), make_row()]})
    o = outcomes(con)
    assert o[f"{F1}:2"] == ("clean", None, None)
    assert o[f"{F1}:3"] == ("superseded", "exact_duplicate", f"{F1}:2")
    assert len(clean(con)) == 1
    assert_one_outcome_per_row(con)


def test_cross_file_exact_duplicate_keeps_earliest_business_date(tmp_path):
    row = make_row(order_date="2026-09-01")
    con = run(tmp_path, {F2: [row], F1: [row]})
    assert clean(con)["ORD-1"][2] == F1
    assert outcomes(con)[f"{F2}:2"] == ("superseded", "exact_duplicate", f"{F1}:2")
    assert_one_outcome_per_row(con)


def test_exact_duplicate_after_standardising(tmp_path):
    con = run(tmp_path, {F1: [make_row(category=" Home "), make_row(category="home")]})
    assert len(clean(con)) == 1
    assert outcomes(con)[f"{F1}:3"][1] == "exact_duplicate"


def test_latest_revision_wins(tmp_path):
    con = run(tmp_path, {
        F1: [make_row(order_id="A", quantity="3"), make_row(order_id="B")],
        F1R2: [make_row(order_id="A", quantity="6"), make_row(order_id="C")],
    })
    c = clean(con)
    assert c["A"] == (6, "completed", F1R2, 2)
    assert c["B"][2] == F1                      # only in r1: kept
    assert c["C"][2] == F1R2                    # only in r2: late-arriving
    assert outcomes(con)[f"{F1}:2"] == ("superseded", "older_revision", f"{F1R2}:2")
    assert_one_outcome_per_row(con)


def test_r10_beats_r2(tmp_path):
    con = run(tmp_path, {
        "orders_2026-09-01_r2.csv": [make_row(quantity="2")],
        "orders_2026-09-01_r10.csv": [make_row(quantity="10")],
    })
    assert clean(con)["ORD-1"][:1] == (10,)


def test_invalid_correction_does_not_replace_valid_row(tmp_path):
    con = run(tmp_path, {F1: [make_row(quantity="3")], F1R2: [make_row(quantity="-1")]})
    assert clean(con)["ORD-1"] == (3, "completed", F1, 1)
    assert outcomes(con)[f"{F1R2}:2"] == ("rejected", "invalid_quantity", None)


def test_in_file_conflict_rejects_both(tmp_path):
    con = run(tmp_path, {F1: [make_row(quantity="1"), make_row(quantity="2")]})
    o = outcomes(con)
    assert o[f"{F1}:2"] == ("rejected", "conflicting_order_id", None)
    assert o[f"{F1}:3"] == ("rejected", "conflicting_order_id", None)
    assert clean(con) == {}
    assert_one_outcome_per_row(con)


def test_cross_date_conflict_keeps_earliest(tmp_path):
    con = run(tmp_path, {
        F1: [make_row(quantity="1")],
        F2: [make_row(quantity="2", order_date="2026-09-02")],
    })
    assert clean(con)["ORD-1"][2] == F1
    assert outcomes(con)[f"{F2}:2"] == ("rejected", "conflicting_order_id", None)
    assert_one_outcome_per_row(con)
