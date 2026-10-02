-- Step 40: latest revision wins, per business date and order_id (FR-015, FR-016).
-- Revision order comes from r<N> in the file name only. An order found only in a
-- lower revision has nothing to compete with and is kept.

CREATE OR REPLACE TABLE step40 AS
SELECT
    *,
    ROW_NUMBER() OVER w  AS rn,
    FIRST_VALUE(row_id) OVER w AS winner
FROM step30_rows
WINDOW w AS (
    PARTITION BY business_date, order_id
    ORDER BY revision DESC, source_file ASC, line_number ASC
);

INSERT INTO superseded_rows
SELECT row_id, 'older_revision', winner FROM step40 WHERE rn > 1;

CREATE OR REPLACE TABLE step40_rows AS
SELECT * EXCLUDE (rn, winner) FROM step40 WHERE rn = 1;

DROP TABLE step40;
