-- Step 60: the published clean orders table, one row per order_id (FR-018).

CREATE OR REPLACE TABLE clean_orders AS
SELECT
    order_id, customer_id, order_date, product_id, category, quantity, unit_price, status,
    CAST(quantity * unit_price AS DECIMAL(18,2)) AS line_revenue,
    source_file, business_date, revision, line_number
FROM final_rows
ORDER BY order_id;
