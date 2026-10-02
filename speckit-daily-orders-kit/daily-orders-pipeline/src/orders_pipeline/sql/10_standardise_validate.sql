-- Step 10: standardise values and apply the row-level rules (FR-004 to FR-012).
-- Standardising is limited to trimming, plus lower-casing category and status.
-- Typed columns are set only when the raw text matches the strict format. TRY_CAST
-- guards against values that are too large for the type.
-- reject_reason is the first failing rule in the FR-012 precedence order.
-- The system clock is never read: "future" means later than the business date.

CREATE OR REPLACE TABLE std_rows AS
WITH trimmed AS (
    SELECT
        row_id, source_file, line_number, business_date, revision, field_count,
        trim(order_id)           AS order_id,
        trim(customer_id)        AS customer_id,
        trim(order_date)         AS order_date_text,
        trim(product_id)         AS product_id,
        lower(trim(category))    AS category,
        trim(quantity)           AS quantity_text,
        trim(unit_price)         AS unit_price_text,
        lower(trim(status))      AS status
    FROM raw_rows
),
typed AS (
    SELECT
        *,
        CASE WHEN regexp_full_match(order_date_text, '\d{4}-\d{2}-\d{2}')
             THEN TRY_CAST(order_date_text AS DATE) END                 AS order_date,
        CASE WHEN regexp_full_match(quantity_text, '[0-9]+')
             THEN TRY_CAST(quantity_text AS INTEGER) END                AS quantity,
        CASE WHEN regexp_full_match(unit_price_text, '[0-9]+(\.[0-9]{1,2})?')
             THEN TRY_CAST(unit_price_text AS DECIMAL(12,2)) END        AS unit_price
    FROM trimmed
)
SELECT
    row_id, source_file, line_number, business_date, revision,
    order_id, customer_id, order_date, product_id, category, quantity, unit_price, status,
    CASE
        WHEN field_count <> 8                                   THEN 'malformed_row'
        WHEN coalesce(order_id, '') = ''                        THEN 'missing_order_id'
        WHEN coalesce(customer_id, '') = ''                     THEN 'missing_customer_id'
        WHEN coalesce(product_id, '') = ''                      THEN 'missing_product_id'
        WHEN order_date IS NULL                                 THEN 'invalid_order_date'
        WHEN order_date > business_date                         THEN 'future_order_date'
        WHEN quantity IS NULL OR quantity < 1                   THEN 'invalid_quantity'
        WHEN unit_price IS NULL OR unit_price <= 0              THEN 'invalid_unit_price'
        WHEN category IS NULL
          OR category NOT IN ('electronics', 'home', 'grocery', 'apparel')
                                                                THEN 'invalid_category'
        WHEN status IS NULL OR status NOT IN ('completed', 'cancelled')
                                                                THEN 'invalid_status'
    END AS reject_reason
FROM typed;
