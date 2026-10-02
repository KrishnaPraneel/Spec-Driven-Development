-- Step 55: exactly one outcome per input row: clean, rejected or superseded.
-- This is the basis for reconciliation (constitution II).

CREATE OR REPLACE TABLE row_outcomes AS
SELECT row_id, 'clean' AS outcome, NULL::VARCHAR AS reason, NULL::VARCHAR AS superseded_by
FROM final_rows
UNION ALL
SELECT row_id, 'rejected', reject_reason, NULL
FROM std_rows
WHERE reject_reason IS NOT NULL
UNION ALL
SELECT row_id, 'rejected', reason, NULL
FROM conflict_rejects
UNION ALL
SELECT row_id, 'superseded', reason, superseded_by
FROM superseded_rows;
