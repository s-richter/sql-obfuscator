-- Extreme Hive sample with multi-layered compliance analytics, map/array expansion,
-- windowing, grouping sets, ranking, and partition overwrite
WITH raw_payment_activity AS (
    SELECT
        p.`payment_event_id`,
        p.`payment_id`,
        p.`account_id`,
        p.`customer_id`,
        p.`origin_country_code`,
        p.`destination_country_code`,
        p.`origin_currency_code`,
        p.`destination_currency_code`,
        p.`payment_method`,
        p.`corridor_code`,
        p.`event_ts`,
        p.`event_date`,
        p.`payment_amount`,
        p.`fee_amount`,
        p.`fx_spread_amount`,
        p.`event_status`,
        p.`screening_payload_json`,
        p.`rule_hits_csv`
    FROM `cross_border_payment_events` p
    WHERE p.`event_date` BETWEEN DATE '2025-07-01' AND DATE '2025-12-31'
      AND p.`event_status` IN ('SETTLED', 'HELD', 'REVIEW')
),
screening_projection AS (
    SELECT
        r.`payment_event_id`,
        r.`payment_id`,
        r.`account_id`,
        r.`customer_id`,
        r.`origin_country_code`,
        r.`destination_country_code`,
        r.`origin_currency_code`,
        r.`destination_currency_code`,
        r.`payment_method`,
        r.`corridor_code`,
        r.`event_ts`,
        r.`event_date`,
        r.`payment_amount`,
        r.`fee_amount`,
        r.`fx_spread_amount`,
        r.`event_status`,
        jt.`screening_outcome`,
        jt.`watchlist_provider`,
        jt.`adverse_media_flag`,
        jt.`beneficiary_risk_band`,
        split(coalesce(r.`rule_hits_csv`, ''), ',') AS `rule_hit_array`
    FROM raw_payment_activity r
    LATERAL VIEW json_tuple(
        r.`screening_payload_json`,
        'screeningOutcome',
        'watchlistProvider',
        'adverseMediaFlag',
        'beneficiaryRiskBand'
    ) jt AS `screening_outcome`, `watchlist_provider`, `adverse_media_flag`, `beneficiary_risk_band`
),
exploded_rule_hits AS (
    SELECT
        sp.`payment_event_id`,
        sp.`payment_id`,
        sp.`account_id`,
        sp.`customer_id`,
        sp.`origin_country_code`,
        sp.`destination_country_code`,
        sp.`origin_currency_code`,
        sp.`destination_currency_code`,
        sp.`payment_method`,
        sp.`corridor_code`,
        sp.`event_ts`,
        sp.`event_date`,
        sp.`payment_amount`,
        sp.`fee_amount`,
        sp.`fx_spread_amount`,
        sp.`event_status`,
        sp.`screening_outcome`,
        sp.`watchlist_provider`,
        sp.`adverse_media_flag`,
        sp.`beneficiary_risk_band`,
        trim(rh.`rule_hit`) AS `rule_hit`
    FROM screening_projection sp
    LATERAL VIEW OUTER explode(sp.`rule_hit_array`) rh AS `rule_hit`
),
rule_event_rollup AS (
    SELECT
        erh.`payment_id`,
        erh.`account_id`,
        erh.`customer_id`,
        erh.`origin_country_code`,
        erh.`destination_country_code`,
        erh.`origin_currency_code`,
        erh.`destination_currency_code`,
        erh.`payment_method`,
        erh.`corridor_code`,
        erh.`screening_outcome`,
        erh.`watchlist_provider`,
        erh.`adverse_media_flag`,
        erh.`beneficiary_risk_band`,
        COUNT(*) AS `event_count`,
        COUNT(DISTINCT erh.`payment_event_id`) AS `distinct_payment_event_count`,
        COUNT(DISTINCT erh.`rule_hit`) AS `distinct_rule_hit_count`,
        collect_set(erh.`rule_hit`) AS `rule_hit_set`,
        SUM(erh.`payment_amount`) AS `total_payment_amount`,
        SUM(erh.`fee_amount`) AS `total_fee_amount`,
        SUM(erh.`fx_spread_amount`) AS `total_fx_spread_amount`,
        MAX(erh.`event_ts`) AS `latest_event_ts`,
        MAX(CASE WHEN erh.`event_status` = 'HELD' THEN 1 ELSE 0 END) AS `any_hold_flag`,
        MAX(CASE WHEN erh.`event_status` = 'REVIEW' THEN 1 ELSE 0 END) AS `any_review_flag`
    FROM exploded_rule_hits erh
    GROUP BY
        erh.`payment_id`,
        erh.`account_id`,
        erh.`customer_id`,
        erh.`origin_country_code`,
        erh.`destination_country_code`,
        erh.`origin_currency_code`,
        erh.`destination_currency_code`,
        erh.`payment_method`,
        erh.`corridor_code`,
        erh.`screening_outcome`,
        erh.`watchlist_provider`,
        erh.`adverse_media_flag`,
        erh.`beneficiary_risk_band`
),
customer_baseline AS (
    SELECT
        c.`customer_id`,
        c.`customer_segment`,
        c.`residence_country_code`,
        c.`kyc_risk_tier`,
        c.`onboarding_channel`,
        c.`is_pep_flag`,
        c.`sanctions_country_touch_flag`
    FROM `customer_compliance_baseline` c
    WHERE c.`snapshot_date` = DATE '2025-12-31'
),
account_baseline AS (
    SELECT
        a.`account_id`,
        a.`portfolio_code`,
        a.`operating_region`,
        a.`product_family`,
        a.`account_status`,
        a.`current_balance_amount`
    FROM `account_financial_baseline` a
    WHERE a.`is_current` = 1
),
joined_compliance AS (
    SELECT
        rer.`payment_id`,
        rer.`account_id`,
        rer.`customer_id`,
        rer.`origin_country_code`,
        rer.`destination_country_code`,
        rer.`origin_currency_code`,
        rer.`destination_currency_code`,
        rer.`payment_method`,
        rer.`corridor_code`,
        rer.`screening_outcome`,
        rer.`watchlist_provider`,
        rer.`adverse_media_flag`,
        rer.`beneficiary_risk_band`,
        rer.`event_count`,
        rer.`distinct_payment_event_count`,
        rer.`distinct_rule_hit_count`,
        size(rer.`rule_hit_set`) AS `rule_hit_set_size`,
        concat_ws('|', sort_array(rer.`rule_hit_set`)) AS `normalized_rule_signature`,
        rer.`total_payment_amount`,
        rer.`total_fee_amount`,
        rer.`total_fx_spread_amount`,
        rer.`latest_event_ts`,
        rer.`any_hold_flag`,
        rer.`any_review_flag`,
        cb.`customer_segment`,
        cb.`residence_country_code`,
        cb.`kyc_risk_tier`,
        cb.`onboarding_channel`,
        cb.`is_pep_flag`,
        cb.`sanctions_country_touch_flag`,
        ab.`portfolio_code`,
        ab.`operating_region`,
        ab.`product_family`,
        ab.`account_status`,
        ab.`current_balance_amount`
    FROM rule_event_rollup rer
    LEFT JOIN customer_baseline cb
        ON rer.`customer_id` = cb.`customer_id`
    LEFT JOIN account_baseline ab
        ON rer.`account_id` = ab.`account_id`
),
scored_compliance AS (
    SELECT
        jc.`payment_id`,
        jc.`account_id`,
        jc.`customer_id`,
        jc.`origin_country_code`,
        jc.`destination_country_code`,
        jc.`origin_currency_code`,
        jc.`destination_currency_code`,
        jc.`payment_method`,
        jc.`corridor_code`,
        jc.`screening_outcome`,
        jc.`watchlist_provider`,
        jc.`adverse_media_flag`,
        jc.`beneficiary_risk_band`,
        jc.`event_count`,
        jc.`distinct_payment_event_count`,
        jc.`distinct_rule_hit_count`,
        jc.`rule_hit_set_size`,
        jc.`normalized_rule_signature`,
        jc.`total_payment_amount`,
        jc.`total_fee_amount`,
        jc.`total_fx_spread_amount`,
        jc.`latest_event_ts`,
        jc.`any_hold_flag`,
        jc.`any_review_flag`,
        jc.`customer_segment`,
        jc.`residence_country_code`,
        jc.`kyc_risk_tier`,
        jc.`onboarding_channel`,
        jc.`is_pep_flag`,
        jc.`sanctions_country_touch_flag`,
        jc.`portfolio_code`,
        jc.`operating_region`,
        jc.`product_family`,
        jc.`account_status`,
        jc.`current_balance_amount`,
        CASE
            WHEN jc.`screening_outcome` = 'BLOCKED' THEN 120.0
            WHEN jc.`screening_outcome` = 'REVIEW' THEN 80.0
            ELSE 30.0
        END
        + (jc.`distinct_rule_hit_count` * 6.0)
        + CASE WHEN jc.`adverse_media_flag` = 'true' THEN 18.0 ELSE 0.0 END
        + CASE WHEN jc.`is_pep_flag` = 1 THEN 20.0 ELSE 0.0 END
        + CASE WHEN jc.`sanctions_country_touch_flag` = 1 THEN 25.0 ELSE 0.0 END
        + CASE WHEN jc.`any_hold_flag` = 1 THEN 12.0 ELSE 0.0 END
        + CASE WHEN jc.`any_review_flag` = 1 THEN 8.0 ELSE 0.0 END
        + CASE
            WHEN jc.`total_payment_amount` >= 500000 THEN 20.0
            WHEN jc.`total_payment_amount` >= 100000 THEN 10.0
            ELSE 0.0
        END AS `composite_compliance_score`,
        ROW_NUMBER() OVER (
            PARTITION BY jc.`customer_id`
            ORDER BY jc.`total_payment_amount` DESC, jc.`latest_event_ts` DESC, jc.`payment_id`
        ) AS `payment_rank_per_customer`,
        DENSE_RANK() OVER (
            PARTITION BY jc.`corridor_code`
            ORDER BY jc.`composite_compliance_score` DESC, jc.`payment_id`
        ) AS `score_rank_per_corridor`,
        SUM(jc.`total_payment_amount`) OVER (
            PARTITION BY jc.`operating_region`, jc.`product_family`
        ) AS `regional_product_total_payment_amount`,
        AVG(jc.`distinct_rule_hit_count`) OVER (
            PARTITION BY jc.`watchlist_provider`
        ) AS `avg_rule_hit_count_by_provider`,
        CUME_DIST() OVER (
            PARTITION BY jc.`portfolio_code`
            ORDER BY jc.`total_payment_amount`
        ) AS `payment_amount_cume_dist_in_portfolio`
    FROM joined_compliance jc
),
compliance_actions AS (
    SELECT
        sc.`payment_id`,
        sc.`account_id`,
        sc.`customer_id`,
        sc.`origin_country_code`,
        sc.`destination_country_code`,
        sc.`origin_currency_code`,
        sc.`destination_currency_code`,
        sc.`payment_method`,
        sc.`corridor_code`,
        sc.`screening_outcome`,
        sc.`watchlist_provider`,
        sc.`adverse_media_flag`,
        sc.`beneficiary_risk_band`,
        sc.`event_count`,
        sc.`distinct_payment_event_count`,
        sc.`distinct_rule_hit_count`,
        sc.`rule_hit_set_size`,
        sc.`normalized_rule_signature`,
        sc.`total_payment_amount`,
        sc.`total_fee_amount`,
        sc.`total_fx_spread_amount`,
        sc.`latest_event_ts`,
        sc.`any_hold_flag`,
        sc.`any_review_flag`,
        sc.`customer_segment`,
        sc.`residence_country_code`,
        sc.`kyc_risk_tier`,
        sc.`onboarding_channel`,
        sc.`is_pep_flag`,
        sc.`sanctions_country_touch_flag`,
        sc.`portfolio_code`,
        sc.`operating_region`,
        sc.`product_family`,
        sc.`account_status`,
        sc.`current_balance_amount`,
        sc.`composite_compliance_score`,
        sc.`payment_rank_per_customer`,
        sc.`score_rank_per_corridor`,
        sc.`regional_product_total_payment_amount`,
        sc.`avg_rule_hit_count_by_provider`,
        sc.`payment_amount_cume_dist_in_portfolio`,
        CASE
            WHEN sc.`composite_compliance_score` >= 175 THEN 'SEVERE'
            WHEN sc.`composite_compliance_score` >= 120 THEN 'HIGH'
            WHEN sc.`composite_compliance_score` >= 75 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS `compliance_band`,
        CASE
            WHEN sc.`screening_outcome` = 'BLOCKED' THEN 'BLOCK_AND_ESCALATE'
            WHEN sc.`is_pep_flag` = 1 AND sc.`composite_compliance_score` >= 120 THEN 'PEP_ESCALATION'
            WHEN sc.`payment_rank_per_customer` = 1 AND sc.`composite_compliance_score` >= 100 THEN 'TOP_PAYMENT_REVIEW'
            WHEN sc.`payment_amount_cume_dist_in_portfolio` >= 0.95 THEN 'LARGE_VALUE_REVIEW'
            ELSE 'STANDARD_QUEUE'
        END AS `recommended_action`
    FROM scored_compliance sc
),
cube_summary AS (
    SELECT
        coalesce(ca.`operating_region`, 'ALL_REGIONS') AS `operating_region`,
        coalesce(ca.`product_family`, 'ALL_PRODUCTS') AS `product_family`,
        coalesce(ca.`compliance_band`, 'ALL_BANDS') AS `compliance_band`,
        COUNT(DISTINCT ca.`payment_id`) AS `cube_payment_count`,
        SUM(ca.`total_payment_amount`) AS `cube_total_payment_amount`,
        SUM(ca.`total_fee_amount`) AS `cube_total_fee_amount`
    FROM compliance_actions ca
    GROUP BY GROUPING SETS (
        (ca.`operating_region`, ca.`product_family`, ca.`compliance_band`),
        (ca.`operating_region`, ca.`product_family`),
        (ca.`operating_region`),
        ()
    )
),
band_pivot AS (
    SELECT
        ca.`portfolio_code`,
        ca.`operating_region`,
        SUM(CASE WHEN ca.`compliance_band` = 'SEVERE' THEN ca.`total_payment_amount` ELSE 0.0 END) AS `severe_payment_amount`,
        SUM(CASE WHEN ca.`compliance_band` = 'HIGH' THEN ca.`total_payment_amount` ELSE 0.0 END) AS `high_payment_amount`,
        SUM(CASE WHEN ca.`compliance_band` = 'MEDIUM' THEN ca.`total_payment_amount` ELSE 0.0 END) AS `medium_payment_amount`,
        SUM(CASE WHEN ca.`compliance_band` = 'LOW' THEN ca.`total_payment_amount` ELSE 0.0 END) AS `low_payment_amount`
    FROM compliance_actions ca
    GROUP BY
        ca.`portfolio_code`,
        ca.`operating_region`
),
final_projection AS (
    SELECT
        ca.`payment_id`,
        ca.`account_id`,
        ca.`customer_id`,
        ca.`origin_country_code`,
        ca.`destination_country_code`,
        ca.`origin_currency_code`,
        ca.`destination_currency_code`,
        ca.`payment_method`,
        ca.`corridor_code`,
        ca.`screening_outcome`,
        ca.`watchlist_provider`,
        ca.`adverse_media_flag`,
        ca.`beneficiary_risk_band`,
        ca.`event_count`,
        ca.`distinct_payment_event_count`,
        ca.`distinct_rule_hit_count`,
        ca.`rule_hit_set_size`,
        ca.`normalized_rule_signature`,
        ca.`total_payment_amount`,
        ca.`total_fee_amount`,
        ca.`total_fx_spread_amount`,
        ca.`latest_event_ts`,
        ca.`any_hold_flag`,
        ca.`any_review_flag`,
        ca.`customer_segment`,
        ca.`residence_country_code`,
        ca.`kyc_risk_tier`,
        ca.`onboarding_channel`,
        ca.`is_pep_flag`,
        ca.`sanctions_country_touch_flag`,
        ca.`portfolio_code`,
        ca.`operating_region`,
        ca.`product_family`,
        ca.`account_status`,
        ca.`current_balance_amount`,
        ca.`composite_compliance_score`,
        ca.`payment_rank_per_customer`,
        ca.`score_rank_per_corridor`,
        ca.`regional_product_total_payment_amount`,
        ca.`avg_rule_hit_count_by_provider`,
        ca.`payment_amount_cume_dist_in_portfolio`,
        ca.`compliance_band`,
        ca.`recommended_action`,
        bp.`severe_payment_amount`,
        bp.`high_payment_amount`,
        bp.`medium_payment_amount`,
        bp.`low_payment_amount`,
        cs.`cube_payment_count`,
        cs.`cube_total_payment_amount`,
        cs.`cube_total_fee_amount`,
        date_format(ca.`latest_event_ts`, 'yyyy-MM-dd HH:mm:ss') AS `latest_event_ts_text`
    FROM compliance_actions ca
    LEFT JOIN band_pivot bp
        ON ca.`portfolio_code` = bp.`portfolio_code`
       AND ca.`operating_region` = bp.`operating_region`
    LEFT JOIN cube_summary cs
        ON ca.`operating_region` = cs.`operating_region`
       AND ca.`product_family` = cs.`product_family`
       AND ca.`compliance_band` = cs.`compliance_band`
)
INSERT OVERWRITE TABLE `analytics`.`cross_border_compliance_mesh`
PARTITION (`snapshot_month` = '2025-12')
SELECT
    fp.`payment_id`,
    fp.`account_id`,
    fp.`customer_id`,
    fp.`origin_country_code`,
    fp.`destination_country_code`,
    fp.`origin_currency_code`,
    fp.`destination_currency_code`,
    fp.`payment_method`,
    fp.`corridor_code`,
    fp.`screening_outcome`,
    fp.`watchlist_provider`,
    fp.`adverse_media_flag`,
    fp.`beneficiary_risk_band`,
    fp.`event_count`,
    fp.`distinct_payment_event_count`,
    fp.`distinct_rule_hit_count`,
    fp.`rule_hit_set_size`,
    fp.`normalized_rule_signature`,
    fp.`total_payment_amount`,
    fp.`total_fee_amount`,
    fp.`total_fx_spread_amount`,
    fp.`latest_event_ts`,
    fp.`any_hold_flag`,
    fp.`any_review_flag`,
    fp.`customer_segment`,
    fp.`residence_country_code`,
    fp.`kyc_risk_tier`,
    fp.`onboarding_channel`,
    fp.`is_pep_flag`,
    fp.`sanctions_country_touch_flag`,
    fp.`portfolio_code`,
    fp.`operating_region`,
    fp.`product_family`,
    fp.`account_status`,
    fp.`current_balance_amount`,
    fp.`composite_compliance_score`,
    fp.`payment_rank_per_customer`,
    fp.`score_rank_per_corridor`,
    fp.`regional_product_total_payment_amount`,
    fp.`avg_rule_hit_count_by_provider`,
    fp.`payment_amount_cume_dist_in_portfolio`,
    fp.`compliance_band`,
    fp.`recommended_action`,
    fp.`severe_payment_amount`,
    fp.`high_payment_amount`,
    fp.`medium_payment_amount`,
    fp.`low_payment_amount`,
    fp.`cube_payment_count`,
    fp.`cube_total_payment_amount`,
    fp.`cube_total_fee_amount`,
    fp.`latest_event_ts_text`
FROM final_projection fp
WHERE fp.`compliance_band` IN ('SEVERE', 'HIGH', 'MEDIUM');
