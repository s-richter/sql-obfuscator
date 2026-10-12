-- Advanced Hive sample with CTEs, nested aggregations, partitions, and window functions
WITH base_orders AS (
    SELECT
        o.`order_id`,
        o.`customer_id`,
        o.`region_id`,
        o.`order_date`,
        o.`order_total`,
        o.`status_code`
    FROM `fact_orders` o
    WHERE o.`order_date` >= DATE '2025-01-01'
),
daily_customer_totals AS (
    SELECT
        bo.`customer_id`,
        bo.`region_id`,
        bo.`order_date`,
        COUNT(*) AS `daily_order_count`,
        SUM(bo.`order_total`) AS `daily_total_amount`
    FROM base_orders bo
    WHERE bo.`status_code` IN ('COMPLETE', 'SHIPPED')
    GROUP BY
        bo.`customer_id`,
        bo.`region_id`,
        bo.`order_date`
),
ranked_customer_days AS (
    SELECT
        dct.`customer_id`,
        dct.`region_id`,
        dct.`order_date`,
        dct.`daily_order_count`,
        dct.`daily_total_amount`,
        ROW_NUMBER() OVER (
            PARTITION BY dct.`customer_id`
            ORDER BY dct.`daily_total_amount` DESC, dct.`order_date` DESC
        ) AS `revenue_rank`,
        SUM(dct.`daily_total_amount`) OVER (
            PARTITION BY dct.`customer_id`
        ) AS `customer_total_amount`
    FROM daily_customer_totals dct
)
INSERT OVERWRITE TABLE `analytics`.`customer_order_summary`
PARTITION (`snapshot_month` = '2025-12')
SELECT
    c.`customer_id`,
    c.`customer_name`,
    r.`region_name`,
    rcd.`order_date` AS `top_order_day`,
    rcd.`daily_order_count`,
    rcd.`daily_total_amount`,
    rcd.`customer_total_amount`,
    CASE
        WHEN rcd.`customer_total_amount` >= 10000 THEN 'PLATINUM'
        WHEN rcd.`customer_total_amount` >= 5000 THEN 'GOLD'
        ELSE 'STANDARD'
    END AS `customer_tier`
FROM ranked_customer_days rcd
INNER JOIN `dim_customer` c
    ON rcd.`customer_id` = c.`customer_id`
LEFT JOIN `dim_region` r
    ON rcd.`region_id` = r.`region_id`
WHERE rcd.`revenue_rank` = 1
  AND rcd.`customer_id` IN (
      SELECT vip.`customer_id`
      FROM `vip_customer_snapshot` vip
      WHERE vip.`is_current` = 1
  );
