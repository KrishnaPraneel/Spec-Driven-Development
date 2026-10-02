-- Step 30: the same order_id more than once in one file with different content
-- (exact duplicates were already collapsed). Nothing is guessed: every such row is
-- rejected (FR-017).

CREATE OR REPLACE TABLE step30 AS
SELECT *, COUNT(*) OVER (PARTITION BY source_file, order_id) AS n
FROM dedup_rows;

CREATE OR REPLACE TABLE conflict_rejects AS
SELECT row_id, 'conflicting_order_id' AS reason
FROM step30
WHERE n > 1;

CREATE OR REPLACE TABLE step30_rows AS
SELECT * EXCLUDE (n) FROM step30 WHERE n = 1;

DROP TABLE step30;
