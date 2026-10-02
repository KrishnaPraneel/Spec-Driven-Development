-- Step 70: reconciliation invariants (constitution II, FR-023, data-model.md).
-- The result is one row of booleans. Any false fails the run.

CREATE OR REPLACE TABLE reconciliation AS
WITH c AS (
    SELECT
        (SELECT count(*) FROM raw_rows)                                     AS n_raw,
        (SELECT count(*) FROM row_outcomes)                                 AS n_out,
        (SELECT count(DISTINCT row_id) FROM row_outcomes)                   AS n_out_ids,
        (SELECT count(*) FROM raw_rows ANTI JOIN row_outcomes USING (row_id)) AS n_missing,
        (SELECT count(*) FROM row_outcomes WHERE outcome = 'clean')         AS n_clean,
        (SELECT count(*) FROM row_outcomes WHERE outcome = 'rejected')      AS n_rejected,
        (SELECT count(*) FROM row_outcomes WHERE outcome = 'superseded')    AS n_superseded,
        (SELECT count(*) FROM clean_orders)                                 AS n_clean_table,
        (SELECT count(DISTINCT order_id) FROM clean_orders)                 AS n_clean_ids,
        (SELECT count(*) FROM rejected_orders)                              AS n_rejected_table,
        (SELECT coalesce(sum(orders), 0) FROM daily_sales_summary)          AS n_summary_orders,
        (SELECT count(*) FROM clean_orders WHERE status = 'completed')      AS n_completed
)
SELECT
    (n_raw = n_out AND n_missing = 0
        AND n_raw = n_clean + n_rejected + n_superseded)  AS counts_balance,
    (n_out = n_out_ids)                                    AS row_ids_unique,
    (n_clean_table = n_clean_ids)                          AS clean_order_id_unique,
    (n_clean_table = n_clean)                              AS clean_count_match,
    (n_rejected_table = n_rejected)                        AS reasons_sum,
    (n_summary_orders = n_completed)                       AS summary_orders_match
FROM c;
