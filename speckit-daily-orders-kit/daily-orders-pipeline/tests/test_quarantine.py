from conftest import EXPECTED_HEADER, make_row, read_columns, read_table, run_cli, write_csv

F1 = "orders_2026-09-01_r1.csv"
COLUMNS = ["source_file", "line_number", "business_date", "revision", "reject_reason",
           *EXPECTED_HEADER, "extra_values"]


def run(tmp_path, text=None, rows=None, name=F1):
    write_csv(tmp_path / "in", name, rows or [], raw_text=text)
    out = tmp_path / "out"
    run_cli("--input", tmp_path / "in", "--output", out, "--max-reject-rate", "1")
    cols = read_columns(out, "rejected_orders")
    return out, [dict(zip(cols, r)) for r in read_table(out, "rejected_orders")]


def test_columns(tmp_path):
    out, _ = run(tmp_path, rows=[make_row(quantity="two")])
    assert read_columns(out, "rejected_orders") == COLUMNS


def test_raw_values_kept_exactly(tmp_path):
    _, rej = run(tmp_path, rows=[make_row(quantity=" two ", category=" HOME ")])
    assert rej[0]["quantity"] == " two "
    assert rej[0]["category"] == " HOME "
    assert rej[0]["reject_reason"] == "invalid_quantity"


def test_physical_line_numbers(tmp_path):
    text = (",".join(EXPECTED_HEADER) + "\n\n"
            + ",".join(make_row(order_id="A", quantity="0")) + "\n")
    _, rej = run(tmp_path, text=text)
    assert (rej[0]["source_file"], rej[0]["line_number"]) == (F1, 3)


def test_malformed_rows(tmp_path):
    _, rej = run(tmp_path, rows=[make_row(order_id="A") + ["x", "y"], make_row()[:6]])
    assert rej[0]["reject_reason"] == "malformed_row"
    assert rej[0]["extra_values"] == "x,y"
    assert rej[1]["reject_reason"] == "malformed_row"
    assert rej[1]["unit_price"] is None and rej[1]["status"] is None


def test_conflicts_appear_and_sorted(tmp_path):
    out, rej = run(tmp_path, rows=[
        make_row(order_id="Z", quantity="0"),
        make_row(order_id="A", quantity="1"),
        make_row(order_id="A", quantity="2"),
        make_row(order_id="B"),
    ])
    assert [(r["line_number"], r["reject_reason"]) for r in rej] == [
        (2, "invalid_quantity"), (3, "conflicting_order_id"), (4, "conflicting_order_id"),
    ]
    clean_lines = {(r[-4], r[-1]) for r in read_table(out, "clean_orders")}
    assert not clean_lines & {(r["source_file"], r["line_number"]) for r in rej}
