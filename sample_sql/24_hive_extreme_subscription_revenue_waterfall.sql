-- Extreme Hive sample with recurring revenue waterfall logic, grouping sets, and layered windows
WITH subscription_snapshots AS (
    SELECT
        s.`account_id`,
        s.`subscription_id`,
        s.`product_family`,
        s.`billing_region`,
        s.`snapshot_month`,
        s.`mrr_amount`,
        s.`is_active`,
        s.`plan_tier`,
        s.`contract_start_date`,
        s.`contract_end_date`
    FROM `finance_subscription_snapshot` s
    WHERE s.`snapshot_month` BETWEEN '2025-01' AND '2025-12'
),
ordered_snapshots AS (
    SELECT
        ss.`account_id`,
        ss.`subscription_id`,
        ss.`product_family`,
        ss.`billing_region`,
        ss.`snapshot_month`,
        ss.`mrr_amount`,
        ss.`is_active`,
        ss.`plan_tier`,
        ss.`contract_start_date`,
        ss.`contract_end_date`,
        LAG(ss.`mrr_amount`) OVER (
            PARTITION BY ss.`subscription_id`
            ORDER BY ss.`snapshot_month`
        ) AS `prev_mrr_amount`,
        LAG(ss.`is_active`) OVER (
            PARTITION BY ss.`subscription_id`
            ORDER BY ss.`snapshot_month`
        ) AS `prev_is_active`,
        LEAD(ss.`mrr_amount`) OVER (
            PARTITION BY ss.`subscription_id`
            ORDER BY ss.`snapshot_month`
        ) AS `next_mrr_amount`
    FROM subscription_snapshots ss
),
waterfall_classification AS (
    SELECT
        os.`account_id`,
        os.`subscription_id`,
        os.`product_family`,
        os.`billing_region`,
        os.`snapshot_month`,
        os.`plan_tier`,
        os.`mrr_amount`,
        coalesce(os.`prev_mrr_amount`, 0.0) AS `prev_mrr_amount`,
        os.`next_mrr_amount`,
        CASE
            WHEN coalesce(os.`prev_is_active`, 0) = 0 AND os.`is_active` = 1 AND os.`mrr_amount` > 0 THEN 'NEW'
            WHEN coalesce(os.`prev_is_active`, 0) = 1 AND os.`is_active` = 0 THEN 'CHURN'
            WHEN os.`mrr_amount` > coalesce(os.`prev_mrr_amount`, 0.0) THEN 'EXPANSION'
            WHEN os.`mrr_amount` < coalesce(os.`prev_mrr_amount`, 0.0) AND os.`is_active` = 1 THEN 'CONTRACTION'
            ELSE 'RETAINED'
        END AS `waterfall_bucket`,
        months_between(
            coalesce(os.`contract_end_date`, last_day(concat(os.`snapshot_month`, '-01'))),
            os.`contract_start_date`
        ) AS `contract_term_months`
    FROM ordered_snapshots os
),
bucket_rollup AS (
    SELECT
        wc.`snapshot_month`,
        wc.`billing_region`,
        wc.`product_family`,
        wc.`waterfall_bucket`,
        COUNT(DISTINCT wc.`subscription_id`) AS `subscription_count`,
        COUNT(DISTINCT wc.`account_id`) AS `account_count`,
        SUM(wc.`mrr_amount`) AS `ending_mrr`,
        SUM(wc.`mrr_amount` - wc.`prev_mrr_amount`) AS `net_mrr_delta`,
        AVG(wc.`contract_term_months`) AS `avg_contract_term_months`
    FROM waterfall_classification wc
    GROUP BY
        wc.`snapshot_month`,
        wc.`billing_region`,
        wc.`product_family`,
        wc.`waterfall_bucket`
),
regional_rollup AS (
    SELECT
        br.`snapshot_month`,
        br.`billing_region`,
        br.`product_family`,
        br.`waterfall_bucket`,
        br.`subscription_count`,
        br.`account_count`,
        br.`ending_mrr`,
        br.`net_mrr_delta`,
        br.`avg_contract_term_months`,
        SUM(br.`ending_mrr`) OVER (
            PARTITION BY br.`snapshot_month`, br.`billing_region`
        ) AS `regional_month_total_mrr`,
        DENSE_RANK() OVER (
            PARTITION BY br.`snapshot_month`, br.`billing_region`
            ORDER BY br.`ending_mrr` DESC, br.`waterfall_bucket`
        ) AS `bucket_rank_in_region`
    FROM bucket_rollup br
),
executive_cube AS (
    SELECT
        coalesce(wc.`snapshot_month`, 'ALL_MONTHS') AS `snapshot_month`,
        coalesce(wc.`billing_region`, 'ALL_REGIONS') AS `billing_region`,
        coalesce(wc.`product_family`, 'ALL_PRODUCTS') AS `product_family`,
        SUM(wc.`mrr_amount`) AS `cube_mrr_amount`,
        COUNT(DISTINCT wc.`account_id`) AS `cube_account_count`
    FROM waterfall_classification wc
    GROUP BY GROUPING SETS (
        (wc.`snapshot_month`, wc.`billing_region`, wc.`product_family`),
        (wc.`snapshot_month`, wc.`billing_region`),
        (wc.`snapshot_month`),
        ()
    )
)
SELECT
    rr.`snapshot_month`,
    rr.`billing_region`,
    rr.`product_family`,
    rr.`waterfall_bucket`,
    rr.`subscription_count`,
    rr.`account_count`,
    rr.`ending_mrr`,
    rr.`net_mrr_delta`,
    rr.`avg_contract_term_months`,
    rr.`regional_month_total_mrr`,
    rr.`bucket_rank_in_region`,
    ec.`cube_mrr_amount`,
    ec.`cube_account_count`
FROM regional_rollup rr
LEFT JOIN executive_cube ec
    ON rr.`snapshot_month` = ec.`snapshot_month`
   AND rr.`billing_region` = ec.`billing_region`
   AND rr.`product_family` = ec.`product_family`
WHERE rr.`bucket_rank_in_region` <= 5;
