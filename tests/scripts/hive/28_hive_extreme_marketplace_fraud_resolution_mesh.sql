-- Final extreme Hive sample with nested fraud signal extraction, path expansion,
-- sequence-aware windows, grouping sets, ranked queues, and partitioned overwrite
WITH raw_order_events AS (
    SELECT
        e.`order_event_id`,
        e.`order_id`,
        e.`merchant_id`,
        e.`buyer_id`,
        e.`fulfillment_site_id`,
        e.`origin_country_code`,
        e.`destination_country_code`,
        e.`payment_method`,
        e.`device_fingerprint`,
        e.`ip_country_code`,
        e.`event_ts`,
        e.`event_date`,
        e.`event_type`,
        e.`event_status`,
        e.`gross_order_amount`,
        e.`discount_amount`,
        e.`shipping_amount`,
        e.`fraud_payload_json`,
        e.`risk_flags_csv`
    FROM `marketplace_order_event_stream` e
    WHERE e.`event_date` BETWEEN DATE '2025-08-01' AND DATE '2025-12-31'
      AND e.`event_status` IN ('PLACED', 'REVIEW', 'APPROVED', 'DECLINED', 'CHARGEBACK')
),
payload_projection AS (
    SELECT
        r.`order_event_id`,
        r.`order_id`,
        r.`merchant_id`,
        r.`buyer_id`,
        r.`fulfillment_site_id`,
        r.`origin_country_code`,
        r.`destination_country_code`,
        r.`payment_method`,
        r.`device_fingerprint`,
        r.`ip_country_code`,
        r.`event_ts`,
        r.`event_date`,
        r.`event_type`,
        r.`event_status`,
        r.`gross_order_amount`,
        r.`discount_amount`,
        r.`shipping_amount`,
        jt.`decision_engine`,
        jt.`review_queue`,
        jt.`identity_cluster`,
        jt.`chargeback_history_band`,
        split(coalesce(r.`risk_flags_csv`, ''), ',') AS `risk_flag_array`
    FROM raw_order_events r
    LATERAL VIEW json_tuple(
        r.`fraud_payload_json`,
        'decisionEngine',
        'reviewQueue',
        'identityCluster',
        'chargebackHistoryBand'
    ) jt AS `decision_engine`, `review_queue`, `identity_cluster`, `chargeback_history_band`
),
exploded_flags AS (
    SELECT
        pp.`order_event_id`,
        pp.`order_id`,
        pp.`merchant_id`,
        pp.`buyer_id`,
        pp.`fulfillment_site_id`,
        pp.`origin_country_code`,
        pp.`destination_country_code`,
        pp.`payment_method`,
        pp.`device_fingerprint`,
        pp.`ip_country_code`,
        pp.`event_ts`,
        pp.`event_date`,
        pp.`event_type`,
        pp.`event_status`,
        pp.`gross_order_amount`,
        pp.`discount_amount`,
        pp.`shipping_amount`,
        pp.`decision_engine`,
        pp.`review_queue`,
        pp.`identity_cluster`,
        pp.`chargeback_history_band`,
        trim(rf.`risk_flag`) AS `risk_flag`
    FROM payload_projection pp
    LATERAL VIEW OUTER explode(pp.`risk_flag_array`) rf AS `risk_flag`
),
ordered_events AS (
    SELECT
        ef.`order_event_id`,
        ef.`order_id`,
        ef.`merchant_id`,
        ef.`buyer_id`,
        ef.`fulfillment_site_id`,
        ef.`origin_country_code`,
        ef.`destination_country_code`,
        ef.`payment_method`,
        ef.`device_fingerprint`,
        ef.`ip_country_code`,
        ef.`event_ts`,
        ef.`event_date`,
        ef.`event_type`,
        ef.`event_status`,
        ef.`gross_order_amount`,
        ef.`discount_amount`,
        ef.`shipping_amount`,
        ef.`decision_engine`,
        ef.`review_queue`,
        ef.`identity_cluster`,
        ef.`chargeback_history_band`,
        ef.`risk_flag`,
        lag(ef.`event_ts`) OVER (
            PARTITION BY ef.`buyer_id`
            ORDER BY ef.`event_ts`, ef.`order_event_id`
        ) AS `prev_event_ts`,
        lag(ef.`gross_order_amount`) OVER (
            PARTITION BY ef.`buyer_id`
            ORDER BY ef.`event_ts`, ef.`order_event_id`
        ) AS `prev_gross_order_amount`,
        lag(ef.`event_status`) OVER (
            PARTITION BY ef.`buyer_id`
            ORDER BY ef.`event_ts`, ef.`order_event_id`
        ) AS `prev_event_status`
    FROM exploded_flags ef
),
burst_sessions AS (
    SELECT
        oe.`order_event_id`,
        oe.`order_id`,
        oe.`merchant_id`,
        oe.`buyer_id`,
        oe.`fulfillment_site_id`,
        oe.`origin_country_code`,
        oe.`destination_country_code`,
        oe.`payment_method`,
        oe.`device_fingerprint`,
        oe.`ip_country_code`,
        oe.`event_ts`,
        oe.`event_date`,
        oe.`event_type`,
        oe.`event_status`,
        oe.`gross_order_amount`,
        oe.`discount_amount`,
        oe.`shipping_amount`,
        oe.`decision_engine`,
        oe.`review_queue`,
        oe.`identity_cluster`,
        oe.`chargeback_history_band`,
        oe.`risk_flag`,
        unix_timestamp(oe.`event_ts`) - unix_timestamp(oe.`prev_event_ts`) AS `seconds_since_prev_event`,
        CASE
            WHEN oe.`prev_event_ts` IS NULL THEN 1
            WHEN unix_timestamp(oe.`event_ts`) - unix_timestamp(oe.`prev_event_ts`) > 1200 THEN 1
            ELSE 0
        END AS `new_burst_marker`,
        coalesce(oe.`gross_order_amount`, 0.0) - coalesce(oe.`prev_gross_order_amount`, 0.0) AS `gross_amount_delta`,
        CASE
            WHEN oe.`prev_event_status` = 'DECLINED' AND oe.`event_status` = 'PLACED' THEN 1
            ELSE 0
        END AS `retry_after_decline_flag`
    FROM ordered_events oe
),
burst_keys AS (
    SELECT
        bs.`order_event_id`,
        bs.`order_id`,
        bs.`merchant_id`,
        bs.`buyer_id`,
        bs.`fulfillment_site_id`,
        bs.`origin_country_code`,
        bs.`destination_country_code`,
        bs.`payment_method`,
        bs.`device_fingerprint`,
        bs.`ip_country_code`,
        bs.`event_ts`,
        bs.`event_date`,
        bs.`event_type`,
        bs.`event_status`,
        bs.`gross_order_amount`,
        bs.`discount_amount`,
        bs.`shipping_amount`,
        bs.`decision_engine`,
        bs.`review_queue`,
        bs.`identity_cluster`,
        bs.`chargeback_history_band`,
        bs.`risk_flag`,
        bs.`seconds_since_prev_event`,
        bs.`new_burst_marker`,
        bs.`gross_amount_delta`,
        bs.`retry_after_decline_flag`,
        sum(bs.`new_burst_marker`) OVER (
            PARTITION BY bs.`buyer_id`
            ORDER BY bs.`event_ts`, bs.`order_event_id`
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS `burst_sequence_id`
    FROM burst_sessions bs
),
burst_rollup AS (
    SELECT
        bk.`buyer_id`,
        bk.`merchant_id`,
        bk.`fulfillment_site_id`,
        bk.`origin_country_code`,
        bk.`destination_country_code`,
        bk.`payment_method`,
        bk.`device_fingerprint`,
        bk.`ip_country_code`,
        bk.`decision_engine`,
        bk.`review_queue`,
        bk.`identity_cluster`,
        bk.`chargeback_history_band`,
        bk.`burst_sequence_id`,
        MIN(bk.`event_ts`) AS `burst_start_ts`,
        MAX(bk.`event_ts`) AS `burst_end_ts`,
        COUNT(*) AS `burst_event_count`,
        COUNT(DISTINCT bk.`order_id`) AS `distinct_order_count`,
        COUNT(DISTINCT bk.`risk_flag`) AS `distinct_risk_flag_count`,
        collect_set(bk.`risk_flag`) AS `risk_flag_set`,
        SUM(bk.`gross_order_amount`) AS `total_gross_order_amount`,
        SUM(bk.`discount_amount`) AS `total_discount_amount`,
        SUM(bk.`shipping_amount`) AS `total_shipping_amount`,
        MAX(abs(bk.`gross_amount_delta`)) AS `max_gross_amount_delta`,
        SUM(CASE WHEN bk.`event_status` = 'DECLINED' THEN 1 ELSE 0 END) AS `decline_event_count`,
        SUM(CASE WHEN bk.`event_status` = 'CHARGEBACK' THEN 1 ELSE 0 END) AS `chargeback_event_count`,
        SUM(bk.`retry_after_decline_flag`) AS `retry_after_decline_count`
    FROM burst_keys bk
    GROUP BY
        bk.`buyer_id`,
        bk.`merchant_id`,
        bk.`fulfillment_site_id`,
        bk.`origin_country_code`,
        bk.`destination_country_code`,
        bk.`payment_method`,
        bk.`device_fingerprint`,
        bk.`ip_country_code`,
        bk.`decision_engine`,
        bk.`review_queue`,
        bk.`identity_cluster`,
        bk.`chargeback_history_band`,
        bk.`burst_sequence_id`
),
buyer_baseline AS (
    SELECT
        b.`buyer_id`,
        b.`buyer_segment`,
        b.`buyer_country_code`,
        b.`kyc_tier`,
        b.`account_age_days`,
        b.`historical_chargeback_rate`
    FROM `buyer_risk_baseline` b
    WHERE b.`snapshot_date` = DATE '2025-12-31'
),
merchant_baseline AS (
    SELECT
        m.`merchant_id`,
        m.`merchant_vertical`,
        m.`merchant_region`,
        m.`merchant_risk_tier`,
        m.`average_ticket_amount`
    FROM `merchant_risk_baseline` m
    WHERE m.`is_current` = 1
),
site_baseline AS (
    SELECT
        s.`fulfillment_site_id`,
        s.`site_name`,
        s.`site_country_code`,
        s.`site_type`,
        s.`network_zone`
    FROM `fulfillment_site_baseline` s
    WHERE s.`snapshot_date` = DATE '2025-12-31'
),
joined_bursts AS (
    SELECT
        br.`buyer_id`,
        br.`merchant_id`,
        br.`fulfillment_site_id`,
        br.`origin_country_code`,
        br.`destination_country_code`,
        br.`payment_method`,
        br.`device_fingerprint`,
        br.`ip_country_code`,
        br.`decision_engine`,
        br.`review_queue`,
        br.`identity_cluster`,
        br.`chargeback_history_band`,
        br.`burst_sequence_id`,
        br.`burst_start_ts`,
        br.`burst_end_ts`,
        br.`burst_event_count`,
        br.`distinct_order_count`,
        br.`distinct_risk_flag_count`,
        size(br.`risk_flag_set`) AS `risk_flag_set_size`,
        concat_ws('|', sort_array(br.`risk_flag_set`)) AS `normalized_risk_flag_signature`,
        br.`total_gross_order_amount`,
        br.`total_discount_amount`,
        br.`total_shipping_amount`,
        br.`max_gross_amount_delta`,
        br.`decline_event_count`,
        br.`chargeback_event_count`,
        br.`retry_after_decline_count`,
        bb.`buyer_segment`,
        bb.`buyer_country_code`,
        bb.`kyc_tier`,
        bb.`account_age_days`,
        bb.`historical_chargeback_rate`,
        mb.`merchant_vertical`,
        mb.`merchant_region`,
        mb.`merchant_risk_tier`,
        mb.`average_ticket_amount`,
        sb.`site_name`,
        sb.`site_country_code`,
        sb.`site_type`,
        sb.`network_zone`
    FROM burst_rollup br
    LEFT JOIN buyer_baseline bb
        ON br.`buyer_id` = bb.`buyer_id`
    LEFT JOIN merchant_baseline mb
        ON br.`merchant_id` = mb.`merchant_id`
    LEFT JOIN site_baseline sb
        ON br.`fulfillment_site_id` = sb.`fulfillment_site_id`
),
scored_bursts AS (
    SELECT
        jb.`buyer_id`,
        jb.`merchant_id`,
        jb.`fulfillment_site_id`,
        jb.`origin_country_code`,
        jb.`destination_country_code`,
        jb.`payment_method`,
        jb.`device_fingerprint`,
        jb.`ip_country_code`,
        jb.`decision_engine`,
        jb.`review_queue`,
        jb.`identity_cluster`,
        jb.`chargeback_history_band`,
        jb.`burst_sequence_id`,
        jb.`burst_start_ts`,
        jb.`burst_end_ts`,
        jb.`burst_event_count`,
        jb.`distinct_order_count`,
        jb.`distinct_risk_flag_count`,
        jb.`risk_flag_set_size`,
        jb.`normalized_risk_flag_signature`,
        jb.`total_gross_order_amount`,
        jb.`total_discount_amount`,
        jb.`total_shipping_amount`,
        jb.`max_gross_amount_delta`,
        jb.`decline_event_count`,
        jb.`chargeback_event_count`,
        jb.`retry_after_decline_count`,
        jb.`buyer_segment`,
        jb.`buyer_country_code`,
        jb.`kyc_tier`,
        jb.`account_age_days`,
        jb.`historical_chargeback_rate`,
        jb.`merchant_vertical`,
        jb.`merchant_region`,
        jb.`merchant_risk_tier`,
        jb.`average_ticket_amount`,
        jb.`site_name`,
        jb.`site_country_code`,
        jb.`site_type`,
        jb.`network_zone`,
        (
            jb.`distinct_risk_flag_count` * 8.0
            + jb.`chargeback_event_count` * 20.0
            + jb.`decline_event_count` * 6.0
            + jb.`retry_after_decline_count` * 9.0
            + CASE WHEN jb.`historical_chargeback_rate` >= 0.05 THEN 25.0 ELSE 0.0 END
            + CASE WHEN jb.`merchant_risk_tier` = 'HIGH' THEN 18.0 ELSE 0.0 END
            + CASE WHEN jb.`account_age_days` <= 30 THEN 12.0 ELSE 0.0 END
            + CASE
                WHEN jb.`total_gross_order_amount` >= 10000 THEN 18.0
                WHEN jb.`total_gross_order_amount` >= 3000 THEN 9.0
                ELSE 0.0
            END
        ) AS `composite_fraud_score`,
        ROW_NUMBER() OVER (
            PARTITION BY jb.`buyer_id`
            ORDER BY jb.`burst_start_ts` DESC, jb.`burst_sequence_id` DESC
        ) AS `burst_recency_rank`,
        DENSE_RANK() OVER (
            PARTITION BY jb.`merchant_id`
            ORDER BY jb.`composite_fraud_score` DESC, jb.`burst_sequence_id`
        ) AS `merchant_score_rank`,
        SUM(jb.`chargeback_event_count`) OVER (
            PARTITION BY jb.`network_zone`, jb.`merchant_vertical`
        ) AS `network_vertical_chargeback_total`,
        AVG(jb.`total_gross_order_amount`) OVER (
            PARTITION BY jb.`merchant_region`
        ) AS `avg_burst_gross_amount_by_region`,
        PERCENT_RANK() OVER (
            PARTITION BY jb.`decision_engine`
            ORDER BY jb.`total_gross_order_amount`
        ) AS `gross_amount_percentile_in_engine`
    FROM joined_bursts jb
),
classified_bursts AS (
    SELECT
        sb.`buyer_id`,
        sb.`merchant_id`,
        sb.`fulfillment_site_id`,
        sb.`origin_country_code`,
        sb.`destination_country_code`,
        sb.`payment_method`,
        sb.`device_fingerprint`,
        sb.`ip_country_code`,
        sb.`decision_engine`,
        sb.`review_queue`,
        sb.`identity_cluster`,
        sb.`chargeback_history_band`,
        sb.`burst_sequence_id`,
        sb.`burst_start_ts`,
        sb.`burst_end_ts`,
        sb.`burst_event_count`,
        sb.`distinct_order_count`,
        sb.`distinct_risk_flag_count`,
        sb.`risk_flag_set_size`,
        sb.`normalized_risk_flag_signature`,
        sb.`total_gross_order_amount`,
        sb.`total_discount_amount`,
        sb.`total_shipping_amount`,
        sb.`max_gross_amount_delta`,
        sb.`decline_event_count`,
        sb.`chargeback_event_count`,
        sb.`retry_after_decline_count`,
        sb.`buyer_segment`,
        sb.`buyer_country_code`,
        sb.`kyc_tier`,
        sb.`account_age_days`,
        sb.`historical_chargeback_rate`,
        sb.`merchant_vertical`,
        sb.`merchant_region`,
        sb.`merchant_risk_tier`,
        sb.`average_ticket_amount`,
        sb.`site_name`,
        sb.`site_country_code`,
        sb.`site_type`,
        sb.`network_zone`,
        sb.`composite_fraud_score`,
        sb.`burst_recency_rank`,
        sb.`merchant_score_rank`,
        sb.`network_vertical_chargeback_total`,
        sb.`avg_burst_gross_amount_by_region`,
        sb.`gross_amount_percentile_in_engine`,
        CASE
            WHEN sb.`composite_fraud_score` >= 150 THEN 'CRITICAL'
            WHEN sb.`composite_fraud_score` >= 100 THEN 'HIGH'
            WHEN sb.`composite_fraud_score` >= 60 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS `fraud_band`,
        CASE
            WHEN sb.`chargeback_event_count` > 0 THEN 'CHARGEBACK_ESCALATION'
            WHEN sb.`burst_recency_rank` = 1 AND sb.`composite_fraud_score` >= 100 THEN 'RECENT_BURST_REVIEW'
            WHEN sb.`gross_amount_percentile_in_engine` >= 0.97 THEN 'LARGE_VALUE_FRAUD_REVIEW'
            ELSE 'STANDARD_QUEUE'
        END AS `recommended_resolution_path`
    FROM scored_bursts sb
),
cube_summary AS (
    SELECT
        coalesce(cb.`network_zone`, 'ALL_NETWORK_ZONES') AS `network_zone`,
        coalesce(cb.`merchant_vertical`, 'ALL_VERTICALS') AS `merchant_vertical`,
        coalesce(cb.`fraud_band`, 'ALL_BANDS') AS `fraud_band`,
        COUNT(DISTINCT cb.`buyer_id`) AS `cube_buyer_count`,
        COUNT(*) AS `cube_burst_count`,
        SUM(cb.`chargeback_event_count`) AS `cube_chargeback_count`
    FROM classified_bursts cb
    GROUP BY GROUPING SETS (
        (cb.`network_zone`, cb.`merchant_vertical`, cb.`fraud_band`),
        (cb.`network_zone`, cb.`merchant_vertical`),
        (cb.`network_zone`),
        ()
    )
),
band_pivot AS (
    SELECT
        cb.`decision_engine`,
        cb.`merchant_region`,
        SUM(CASE WHEN cb.`fraud_band` = 'CRITICAL' THEN cb.`total_gross_order_amount` ELSE 0.0 END) AS `critical_gross_amount`,
        SUM(CASE WHEN cb.`fraud_band` = 'HIGH' THEN cb.`total_gross_order_amount` ELSE 0.0 END) AS `high_gross_amount`,
        SUM(CASE WHEN cb.`fraud_band` = 'MEDIUM' THEN cb.`total_gross_order_amount` ELSE 0.0 END) AS `medium_gross_amount`,
        SUM(CASE WHEN cb.`fraud_band` = 'LOW' THEN cb.`total_gross_order_amount` ELSE 0.0 END) AS `low_gross_amount`
    FROM classified_bursts cb
    GROUP BY
        cb.`decision_engine`,
        cb.`merchant_region`
),
final_projection AS (
    SELECT
        cb.`buyer_id`,
        cb.`merchant_id`,
        cb.`fulfillment_site_id`,
        cb.`origin_country_code`,
        cb.`destination_country_code`,
        cb.`payment_method`,
        cb.`device_fingerprint`,
        cb.`ip_country_code`,
        cb.`decision_engine`,
        cb.`review_queue`,
        cb.`identity_cluster`,
        cb.`chargeback_history_band`,
        cb.`burst_sequence_id`,
        cb.`burst_start_ts`,
        cb.`burst_end_ts`,
        cb.`burst_event_count`,
        cb.`distinct_order_count`,
        cb.`distinct_risk_flag_count`,
        cb.`risk_flag_set_size`,
        cb.`normalized_risk_flag_signature`,
        cb.`total_gross_order_amount`,
        cb.`total_discount_amount`,
        cb.`total_shipping_amount`,
        cb.`max_gross_amount_delta`,
        cb.`decline_event_count`,
        cb.`chargeback_event_count`,
        cb.`retry_after_decline_count`,
        cb.`buyer_segment`,
        cb.`buyer_country_code`,
        cb.`kyc_tier`,
        cb.`account_age_days`,
        cb.`historical_chargeback_rate`,
        cb.`merchant_vertical`,
        cb.`merchant_region`,
        cb.`merchant_risk_tier`,
        cb.`average_ticket_amount`,
        cb.`site_name`,
        cb.`site_country_code`,
        cb.`site_type`,
        cb.`network_zone`,
        cb.`composite_fraud_score`,
        cb.`burst_recency_rank`,
        cb.`merchant_score_rank`,
        cb.`network_vertical_chargeback_total`,
        cb.`avg_burst_gross_amount_by_region`,
        cb.`gross_amount_percentile_in_engine`,
        cb.`fraud_band`,
        cb.`recommended_resolution_path`,
        bp.`critical_gross_amount`,
        bp.`high_gross_amount`,
        bp.`medium_gross_amount`,
        bp.`low_gross_amount`,
        cu.`cube_buyer_count`,
        cu.`cube_burst_count`,
        cu.`cube_chargeback_count`,
        date_format(cb.`burst_end_ts`, 'yyyy-MM-dd HH:mm:ss') AS `burst_end_ts_text`
    FROM classified_bursts cb
    LEFT JOIN band_pivot bp
        ON cb.`decision_engine` = bp.`decision_engine`
       AND cb.`merchant_region` = bp.`merchant_region`
    LEFT JOIN cube_summary cu
        ON cb.`network_zone` = cu.`network_zone`
       AND cb.`merchant_vertical` = cu.`merchant_vertical`
       AND cb.`fraud_band` = cu.`fraud_band`
)
INSERT OVERWRITE TABLE `analytics`.`marketplace_fraud_resolution_mesh`
PARTITION (`snapshot_month` = '2025-12')
SELECT
    fp.`buyer_id`,
    fp.`merchant_id`,
    fp.`fulfillment_site_id`,
    fp.`origin_country_code`,
    fp.`destination_country_code`,
    fp.`payment_method`,
    fp.`device_fingerprint`,
    fp.`ip_country_code`,
    fp.`decision_engine`,
    fp.`review_queue`,
    fp.`identity_cluster`,
    fp.`chargeback_history_band`,
    fp.`burst_sequence_id`,
    fp.`burst_start_ts`,
    fp.`burst_end_ts`,
    fp.`burst_event_count`,
    fp.`distinct_order_count`,
    fp.`distinct_risk_flag_count`,
    fp.`risk_flag_set_size`,
    fp.`normalized_risk_flag_signature`,
    fp.`total_gross_order_amount`,
    fp.`total_discount_amount`,
    fp.`total_shipping_amount`,
    fp.`max_gross_amount_delta`,
    fp.`decline_event_count`,
    fp.`chargeback_event_count`,
    fp.`retry_after_decline_count`,
    fp.`buyer_segment`,
    fp.`buyer_country_code`,
    fp.`kyc_tier`,
    fp.`account_age_days`,
    fp.`historical_chargeback_rate`,
    fp.`merchant_vertical`,
    fp.`merchant_region`,
    fp.`merchant_risk_tier`,
    fp.`average_ticket_amount`,
    fp.`site_name`,
    fp.`site_country_code`,
    fp.`site_type`,
    fp.`network_zone`,
    fp.`composite_fraud_score`,
    fp.`burst_recency_rank`,
    fp.`merchant_score_rank`,
    fp.`network_vertical_chargeback_total`,
    fp.`avg_burst_gross_amount_by_region`,
    fp.`gross_amount_percentile_in_engine`,
    fp.`fraud_band`,
    fp.`recommended_resolution_path`,
    fp.`critical_gross_amount`,
    fp.`high_gross_amount`,
    fp.`medium_gross_amount`,
    fp.`low_gross_amount`,
    fp.`cube_buyer_count`,
    fp.`cube_burst_count`,
    fp.`cube_chargeback_count`,
    fp.`burst_end_ts_text`
FROM final_projection fp
WHERE fp.`fraud_band` IN ('CRITICAL', 'HIGH', 'MEDIUM');
