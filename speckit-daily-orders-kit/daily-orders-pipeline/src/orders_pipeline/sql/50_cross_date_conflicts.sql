-- Step 50: the same order_id in files for different business dates (FR-017a).
-- The row from the earliest business date is kept. Rows from later business
-- dates are rejected.

CREATE OR REPLACE TABLE step50 AS
SELECT
    *,
    ROW_NUMBER() OVER (
        PARTITION BY order_id
        ORDER BY business_date ASC, revision DESC, source_file ASC, line_number ASC
    ) AS rn
FROM step40_rows;

INSERT INTO conflict_rejects
SELECT row_id, 'conflicting_order_id' FROM step50 WHERE rn > 1;

CREATE OR REPLACE TABLE final_rows AS
SELECT * EXCLUDE (rn) FROM step50 WHERE rn = 1;

DROP TABLE step50;
