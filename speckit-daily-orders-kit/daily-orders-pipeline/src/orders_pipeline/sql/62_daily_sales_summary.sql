-- Step 62: the published daily sales summary (FR-020). It is built from completed
-- clean orders only; cancelled orders count toward no figure (spec Q1).

CREATE OR REPLACE TABLE daily_sales_summary AS
SELECT
    order_date,
    category,
    COUNT(*)::BIGINT                          AS orders,
    SUM(quantity)::BIGINT                     AS units,
    CAST(SUM(line_revenue) AS DECIMAL(18,2))  AS revenue
FROM clean_orders
WHERE status = 'completed'
GROUP BY order_date, category
ORDER BY order_date, category;
