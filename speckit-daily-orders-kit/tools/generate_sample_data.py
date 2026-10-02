"""Generate the Daily Orders sample data set (deterministic).

The files contain deliberately planted data-quality problems so that learners can
check whether their spec, plan and implementation handle them. Every planted problem
is listed in PLANTED_ISSUES at the bottom and in Appendix C of the course guide.

Usage:  python tools/generate_sample_data.py [output_dir]
"""
import csv
import random
import sys
from pathlib import Path

SEED = 20260901
HEADER = ["order_id", "customer_id", "order_date", "product_id", "category",
          "quantity", "unit_price", "status"]

# product_id -> (category, unit_price)
PRODUCTS = {
    "P100": ("electronics", "199.99"), "P101": ("electronics", "49.50"),
    "P102": ("electronics", "89.00"),  "P200": ("home", "34.25"),
    "P201": ("home", "120.00"),        "P202": ("home", "15.75"),
    "P300": ("grocery", "4.20"),       "P301": ("grocery", "9.80"),
    "P302": ("grocery", "2.15"),       "P400": ("apparel", "59.90"),
    "P401": ("apparel", "24.99"),      "P402": ("apparel", "75.00"),
}


def make_rows(rng, start_id, n, order_date):
    rows = []
    for i in range(n):
        pid = rng.choice(sorted(PRODUCTS))
        cat, price = PRODUCTS[pid]
        status = "cancelled" if rng.random() < 0.08 else "completed"
        rows.append([f"ORD-{start_id + i:06d}", f"C{rng.randint(1, 60):04d}", order_date,
                     pid, cat, str(rng.randint(1, 5)), price, status])
    return rows


def write(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    # ---- Base (clean) data -------------------------------------------------
    d1 = make_rows(rng, 1, 40, "2026-09-01")        # ORD-000001..000040
    d2 = make_rows(rng, 101, 45, "2026-09-02")      # ORD-000101..000145
    d3 = make_rows(rng, 201, 40, "2026-09-03")      # ORD-000201..000240
    late_new = make_rows(rng, 41, 8, "2026-09-01")  # ORD-000041..000048 (missing from r1)

    # ---- File 1: orders_2026-09-01_r1.csv ---------------------------------
    d1[12][5] = "-2"                       # (3) negative quantity
    d1[20][2] = "2026-13-45"               # (4) unparseable date
    d1[25][4] = " Electronics "            # (5) messy category  -> normalise, not reject
    d1[30][7] = "Completed"                # (6) messy status     -> normalise, not reject

    # ---- File 2: orders_2026-09-02_r1.csv ---------------------------------
    d2[5][1] = ""                          # (7) missing customer_id
    d2[10][5] = "0"                        # (8) zero quantity
    d2[15][6] = "-9.99"                    # (9) negative unit price
    d2[20][2] = "02/09/2026"               # (10) non-ISO date format
    d2[25][0] = ""                         # (11) missing order_id
    d2[30][4] = "HOME"                     # (12) messy category  -> normalise
    dup_from_d2 = list(d2[35])             # kept for cross-file duplicate in file 3

    # ---- File 3: orders_2026-09-03_r1.csv ---------------------------------
    d3[8][2] = "2026-12-25"                # (13) future order date (> file business date)
    d3[18][5] = "two"                      # (14) non-numeric quantity
    d3[28][4] = "apparel "                 # (15) messy category  -> normalise

    # ---- File 4: orders_2026-09-01_r2.csv (late-arriving revision) --------
    correction_qty = list(d1[2])           # (17) correction: quantity changed
    correction_qty[5] = str(int(d1[2][5]) + 3)
    correction_cancel = list(d1[15])       # (18) correction: order now cancelled
    correction_cancel[7] = "cancelled"
    r2 = late_new + [correction_qty, correction_cancel]

    # Exact duplicates are appended last so row positions above stay stable.
    d1.append(list(d1[3]))                 # (1) exact duplicate within file
    d1.append(list(d1[7]))                 # (2) exact duplicate within file
    d3.append(dup_from_d2)                 # (16) exact duplicate of an order in file 2

    write(out / "orders_2026-09-01_r1.csv", d1)
    write(out / "orders_2026-09-02_r1.csv", d2)
    write(out / "orders_2026-09-03_r1.csv", d3)
    write(out / "orders_2026-09-01_r2.csv", r2)
    print(f"Wrote 4 files to {out}")


PLANTED_ISSUES = """
 #  File                     Problem                                  Expected handling
 1  2026-09-01_r1            exact duplicate row (in-file)            de-duplicate
 2  2026-09-01_r1            exact duplicate row (in-file)            de-duplicate
 3  2026-09-01_r1            quantity = -2                            reject: invalid_quantity
 4  2026-09-01_r1            order_date = 2026-13-45                  reject: invalid_order_date
 5  2026-09-01_r1            category ' Electronics '                 normalise (trim + lower-case)
 6  2026-09-01_r1            status 'Completed'                       normalise (lower-case)
 7  2026-09-02_r1            customer_id blank                        reject: missing_customer_id
 8  2026-09-02_r1            quantity = 0                             reject: invalid_quantity
 9  2026-09-02_r1            unit_price = -9.99                       reject: invalid_unit_price
10  2026-09-02_r1            order_date = 02/09/2026                  reject: invalid_order_date
11  2026-09-02_r1            order_id blank                           reject: missing_order_id
12  2026-09-02_r1            category 'HOME'                          normalise
13  2026-09-03_r1            order_date = 2026-12-25 (future)         reject: future_order_date
14  2026-09-03_r1            quantity = 'two'                         reject: invalid_quantity
15  2026-09-03_r1            category 'apparel '                      normalise
16  2026-09-03_r1            exact duplicate of a 09-02 order         de-duplicate (cross-file)
17  2026-09-01_r2            correction: quantity changed             latest revision wins
18  2026-09-01_r2            correction: status -> cancelled          latest revision wins
--  2026-09-01_r2            8 new orders missing from r1             include (late-arriving data)
"""

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/incoming")
