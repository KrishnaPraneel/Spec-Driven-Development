-- Step 20: collapse exact duplicates (FR-014) among valid rows.
-- Rows identical in all 8 standardised columns are one group. The row kept is the
-- earliest business date, then the highest revision, which matches the revision
-- rule (step 40) and the cross-date rule (step 50). The other rows are superseded.

CREATE OR REPLACE TABLE step20 AS
SELECT
    *,
    ROW_NUMBER() OVER w  AS rn,
    FIRST_VALUE(row_id) OVER w AS winner
FROM std_rows
WHERE reject_reason IS NULL
WINDOW w AS (
    PARTITION BY order_id, customer_id, order_date, product_id,
                 category, quantity, unit_price, status
    ORDER BY business_date ASC, revision DESC, source_file ASC, line_number ASC
);

CREATE OR REPLACE TABLE superseded_rows AS
SELECT row_id, 'exact_duplicate' AS reason, winner AS superseded_by
FROM step20
WHERE rn > 1;

CREATE OR REPLACE TABLE dedup_rows AS
SELECT * EXCLUDE (rn, winner) FROM step20 WHERE rn = 1;

DROP TABLE step20;
