-- Step 61: the published quarantine table (FR-019). It has one row per rejected
-- input row, with the raw values exactly as received and one reason code.

CREATE OR REPLACE TABLE rejected_orders AS
SELECT
    r.source_file, r.line_number, r.business_date, r.revision,
    o.reason AS reject_reason,
    r.order_id, r.customer_id, r.order_date, r.product_id,
    r.category, r.quantity, r.unit_price, r.status,
    r.extra_values
FROM row_outcomes o
JOIN raw_rows r USING (row_id)
WHERE o.outcome = 'rejected'
ORDER BY r.source_file, r.line_number;
