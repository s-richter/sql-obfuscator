-- Extreme Hive sample with recursive-like layered CTEs, semi-structured extraction,
-- lateral views, window functions, grouping sets, pivot-style aggregation, and partitioned insert
WITH raw_case_events AS (
    SELECT
        e.`case_event_id`,
        e.`case_id`,
        e.`account_id`,
        e.`counterparty_id`,
        e.`jurisdiction_code`,
        e.`event_ts`,
        e.`event_date`,
        e.`event_type`,
        e.`event_status`,
        e.`severity_score`,
        e.`loss_amount`,
        e.`exposure_amount`,
        e.`payload_json`,
        e.`tag_csv`,
        e.`analyst_notes`
    FROM `risk_case_event_stream` e
    WHERE e.`event_date` BETWEEN DATE '2025-08-01' AND DATE '2025-12-31'
      AND e.`event_status` <> 'IGNORED'
),
parsed_payload AS (
    SELECT
        r.`case_event_id`,
        r.`case_id`,
        r.`account_id`,
        r.`counterparty_id`,
        r.`jurisdiction_code`,
        r.`event_ts`,
        r.`event_date`,
        r.`event_type`,
        r.`event_status`,
        r.`severity_score`,
        r.`loss_amount`,
        r.`exposure_amount`,
        r.`analyst_notes`,
        jt.`alert_family`,
        jt.`source_model`,
        jt.`review_queue`,
        jt.`entity_cluster`,
        split(coalesce(r.`tag_csv`, ''), ',') AS `tag_array`
    FROM raw_case_events r
    LATERAL VIEW json_tuple(
        r.`payload_json`,
        'alertFamily',
        'sourceModel',
        'reviewQueue',
        'entityCluster'
    ) jt AS `alert_family`, `source_model`, `review_queue`, `entity_cluster`
),
exploded_tags AS (
    SELECT
        p.`case_event_id`,
        p.`case_id`,
        p.`account_id`,
        p.`counterparty_id`,
        p.`jurisdiction_code`,
        p.`event_ts`,
        p.`event_date`,
        p.`event_type`,
        p.`event_status`,
        p.`severity_score`,
        p.`loss_amount`,
        p.`exposure_amount`,
        p.`analyst_notes`,
        p.`alert_family`,
        p.`source_model`,
        p.`review_queue`,
        p.`entity_cluster`,
        trim(t.`risk_tag`) AS `risk_tag`
    FROM parsed_payload p
    LATERAL VIEW OUTER explode(p.`tag_array`) t AS `risk_tag`
),
tag_rollup AS (
    SELECT
        et.`case_id`,
        et.`account_id`,
        et.`counterparty_id`,
        et.`jurisdiction_code`,
        et.`alert_family`,
        et.`source_model`,
        et.`review_queue`,
        et.`entity_cluster`,
        COUNT(*) AS `event_count`,
        COUNT(DISTINCT et.`case_event_id`) AS `distinct_event_count`,
        COUNT(DISTINCT et.`risk_tag`) AS `distinct_risk_tag_count`,
        collect_set(et.`risk_tag`) AS `risk_tag_set`,
        SUM(coalesce(et.`loss_amount`, 0.0)) AS `total_loss_amount`,
        SUM(coalesce(et.`exposure_amount`, 0.0)) AS `total_exposure_amount`,
        MAX(et.`severity_score`) AS `max_severity_score`,
        AVG(et.`severity_score`) AS `avg_severity_score`,
        MAX(et.`event_ts`) AS `latest_event_ts`
    FROM exploded_tags et
    GROUP BY
        et.`case_id`,
        et.`account_id`,
        et.`counterparty_id`,
        et.`jurisdiction_code`,
        et.`alert_family`,
        et.`source_model`,
        et.`review_queue`,
        et.`entity_cluster`
),
account_baseline AS (
    SELECT
        ab.`account_id`,
        ab.`portfolio_code`,
        ab.`segment_name`,
        ab.`region_group`,
        ab.`risk_tier`,
        ab.`onboarding_date`,
        ab.`current_balance_amount`
    FROM `account_risk_baseline` ab
    WHERE ab.`is_current` = 1
),
counterparty_baseline AS (
    SELECT
        cb.`counterparty_id`,
        cb.`counterparty_name`,
        cb.`industry_group`,
        cb.`sanctions_watchlist_flag`,
        cb.`pep_flag`,
        cb.`country_of_risk`
    FROM `counterparty_risk_baseline` cb
    WHERE cb.`snapshot_date` = DATE '2025-12-31'
),
joined_signals AS (
    SELECT
        tr.`case_id`,
        tr.`account_id`,
        tr.`counterparty_id`,
        tr.`jurisdiction_code`,
        tr.`alert_family`,
        tr.`source_model`,
        tr.`review_queue`,
        tr.`entity_cluster`,
        tr.`event_count`,
        tr.`distinct_event_count`,
        tr.`distinct_risk_tag_count`,
        size(tr.`risk_tag_set`) AS `risk_tag_set_size`,
        concat_ws('|', sort_array(tr.`risk_tag_set`)) AS `normalized_risk_tag_signature`,
        tr.`total_loss_amount`,
        tr.`total_exposure_amount`,
        tr.`max_severity_score`,
        tr.`avg_severity_score`,
        tr.`latest_event_ts`,
        ab.`portfolio_code`,
        ab.`segment_name`,
        ab.`region_group`,
        ab.`risk_tier`,
        ab.`onboarding_date`,
        ab.`current_balance_amount`,
        cb.`counterparty_name`,
        cb.`industry_group`,
        cb.`sanctions_watchlist_flag`,
        cb.`pep_flag`,
        cb.`country_of_risk`
    FROM tag_rollup tr
    LEFT JOIN account_baseline ab
        ON tr.`account_id` = ab.`account_id`
    LEFT JOIN counterparty_baseline cb
        ON tr.`counterparty_id` = cb.`counterparty_id`
),
scored_cases AS (
    SELECT
        js.`case_id`,
        js.`account_id`,
        js.`counterparty_id`,
        js.`jurisdiction_code`,
        js.`alert_family`,
        js.`source_model`,
        js.`review_queue`,
        js.`entity_cluster`,
        js.`event_count`,
        js.`distinct_event_count`,
        js.`distinct_risk_tag_count`,
        js.`risk_tag_set_size`,
        js.`normalized_risk_tag_signature`,
        js.`total_loss_amount`,
        js.`total_exposure_amount`,
        js.`max_severity_score`,
        js.`avg_severity_score`,
        js.`latest_event_ts`,
        js.`portfolio_code`,
        js.`segment_name`,
        js.`region_group`,
        js.`risk_tier`,
        js.`current_balance_amount`,
        js.`counterparty_name`,
        js.`industry_group`,
        js.`sanctions_watchlist_flag`,
        js.`pep_flag`,
        js.`country_of_risk`,
        CASE
            WHEN js.`total_exposure_amount` = 0 THEN js.`max_severity_score`
            ELSE
                js.`max_severity_score`
                + (js.`avg_severity_score` * 0.25)
                + (cast(js.`total_loss_amount` AS double) / greatest(cast(js.`total_exposure_amount` AS double), 1.0) * 100.0)
                + CASE WHEN js.`sanctions_watchlist_flag` = 1 THEN 15.0 ELSE 0.0 END
                + CASE WHEN js.`pep_flag` = 1 THEN 10.0 ELSE 0.0 END
        END AS `composite_risk_score`,
        ROW_NUMBER() OVER (
            PARTITION BY js.`account_id`
            ORDER BY js.`max_severity_score` DESC, js.`latest_event_ts` DESC, js.`case_id`
        ) AS `risk_rank_per_account`,
        DENSE_RANK() OVER (
            PARTITION BY js.`jurisdiction_code`
            ORDER BY js.`total_exposure_amount` DESC, js.`case_id`
        ) AS `exposure_rank_per_jurisdiction`,
        SUM(js.`total_exposure_amount`) OVER (
            PARTITION BY js.`region_group`, js.`alert_family`
        ) AS `regional_alert_family_exposure`,
        AVG(js.`max_severity_score`) OVER (
            PARTITION BY js.`source_model`
        ) AS `avg_severity_by_source_model`,
        PERCENT_RANK() OVER (
            PARTITION BY js.`portfolio_code`
            ORDER BY js.`total_loss_amount`
        ) AS `loss_percentile_in_portfolio`
    FROM joined_signals js
),
case_enrichment AS (
    SELECT
        sc.`case_id`,
        sc.`account_id`,
        sc.`counterparty_id`,
        sc.`jurisdiction_code`,
        sc.`alert_family`,
        sc.`source_model`,
        sc.`review_queue`,
        sc.`entity_cluster`,
        sc.`event_count`,
        sc.`distinct_event_count`,
        sc.`distinct_risk_tag_count`,
        sc.`risk_tag_set_size`,
        sc.`normalized_risk_tag_signature`,
        sc.`total_loss_amount`,
        sc.`total_exposure_amount`,
        sc.`max_severity_score`,
        sc.`avg_severity_score`,
        sc.`composite_risk_score`,
        sc.`latest_event_ts`,
        sc.`portfolio_code`,
        sc.`segment_name`,
        sc.`region_group`,
        sc.`risk_tier`,
        sc.`current_balance_amount`,
        sc.`counterparty_name`,
        sc.`industry_group`,
        sc.`sanctions_watchlist_flag`,
        sc.`pep_flag`,
        sc.`country_of_risk`,
        sc.`risk_rank_per_account`,
        sc.`exposure_rank_per_jurisdiction`,
        sc.`regional_alert_family_exposure`,
        sc.`avg_severity_by_source_model`,
        sc.`loss_percentile_in_portfolio`,
        CASE
            WHEN sc.`composite_risk_score` >= 140 THEN 'RED'
            WHEN sc.`composite_risk_score` >= 100 THEN 'AMBER'
            WHEN sc.`composite_risk_score` >= 70 THEN 'YELLOW'
            ELSE 'GREEN'
        END AS `risk_band`,
        CASE
            WHEN sc.`risk_rank_per_account` = 1 AND sc.`composite_risk_score` >= 100 THEN 'PRIORITY_REVIEW'
            WHEN sc.`sanctions_watchlist_flag` = 1 OR sc.`pep_flag` = 1 THEN 'REGULATORY_ESCALATION'
            WHEN sc.`loss_percentile_in_portfolio` >= 0.90 THEN 'LOSS_SPIKE_REVIEW'
            ELSE 'STANDARD_REVIEW'
        END AS `triage_action`
    FROM scored_cases sc
),
jurisdiction_cube AS (
    SELECT
        coalesce(ce.`jurisdiction_code`, 'ALL_JURISDICTIONS') AS `jurisdiction_code`,
        coalesce(ce.`region_group`, 'ALL_REGIONS') AS `region_group`,
        coalesce(ce.`alert_family`, 'ALL_ALERT_FAMILIES') AS `alert_family`,
        COUNT(DISTINCT ce.`case_id`) AS `cube_case_count`,
        SUM(ce.`total_exposure_amount`) AS `cube_total_exposure_amount`,
        SUM(ce.`total_loss_amount`) AS `cube_total_loss_amount`
    FROM case_enrichment ce
    GROUP BY GROUPING SETS (
        (ce.`jurisdiction_code`, ce.`region_group`, ce.`alert_family`),
        (ce.`jurisdiction_code`, ce.`region_group`),
        (ce.`jurisdiction_code`),
        ()
    )
),
pivot_ready AS (
    SELECT
        ce.`portfolio_code`,
        ce.`region_group`,
        ce.`risk_band`,
        ce.`total_exposure_amount`
    FROM case_enrichment ce
),
pivoted_risk_bands AS (
    SELECT
        pr.`portfolio_code`,
        pr.`region_group`,
        SUM(CASE WHEN pr.`risk_band` = 'RED' THEN pr.`total_exposure_amount` ELSE 0.0 END) AS `red_exposure_amount`,
        SUM(CASE WHEN pr.`risk_band` = 'AMBER' THEN pr.`total_exposure_amount` ELSE 0.0 END) AS `amber_exposure_amount`,
        SUM(CASE WHEN pr.`risk_band` = 'YELLOW' THEN pr.`total_exposure_amount` ELSE 0.0 END) AS `yellow_exposure_amount`,
        SUM(CASE WHEN pr.`risk_band` = 'GREEN' THEN pr.`total_exposure_amount` ELSE 0.0 END) AS `green_exposure_amount`
    FROM pivot_ready pr
    GROUP BY
        pr.`portfolio_code`,
        pr.`region_group`
),
final_projection AS (
    SELECT
        ce.`case_id`,
        ce.`account_id`,
        ce.`counterparty_id`,
        ce.`jurisdiction_code`,
        ce.`alert_family`,
        ce.`source_model`,
        ce.`review_queue`,
        ce.`entity_cluster`,
        ce.`portfolio_code`,
        ce.`segment_name`,
        ce.`region_group`,
        ce.`risk_tier`,
        ce.`counterparty_name`,
        ce.`industry_group`,
        ce.`country_of_risk`,
        ce.`event_count`,
        ce.`distinct_event_count`,
        ce.`distinct_risk_tag_count`,
        ce.`risk_tag_set_size`,
        ce.`normalized_risk_tag_signature`,
        ce.`total_loss_amount`,
        ce.`total_exposure_amount`,
        ce.`max_severity_score`,
        ce.`avg_severity_score`,
        ce.`composite_risk_score`,
        ce.`risk_rank_per_account`,
        ce.`exposure_rank_per_jurisdiction`,
        ce.`regional_alert_family_exposure`,
        ce.`avg_severity_by_source_model`,
        ce.`loss_percentile_in_portfolio`,
        ce.`risk_band`,
        ce.`triage_action`,
        pb.`red_exposure_amount`,
        pb.`amber_exposure_amount`,
        pb.`yellow_exposure_amount`,
        pb.`green_exposure_amount`,
        jc.`cube_case_count`,
        jc.`cube_total_exposure_amount`,
        jc.`cube_total_loss_amount`,
        date_format(ce.`latest_event_ts`, 'yyyy-MM-dd HH:mm:ss') AS `latest_event_ts_text`
    FROM case_enrichment ce
    LEFT JOIN pivoted_risk_bands pb
        ON ce.`portfolio_code` = pb.`portfolio_code`
       AND ce.`region_group` = pb.`region_group`
    LEFT JOIN jurisdiction_cube jc
        ON ce.`jurisdiction_code` = jc.`jurisdiction_code`
       AND ce.`region_group` = jc.`region_group`
       AND ce.`alert_family` = jc.`alert_family`
)
INSERT OVERWRITE TABLE `analytics`.`federated_risk_signal_fabric`
PARTITION (`snapshot_month` = '2025-12')
SELECT
    fp.`case_id`,
    fp.`account_id`,
    fp.`counterparty_id`,
    fp.`jurisdiction_code`,
    fp.`alert_family`,
    fp.`source_model`,
    fp.`review_queue`,
    fp.`entity_cluster`,
    fp.`portfolio_code`,
    fp.`segment_name`,
    fp.`region_group`,
    fp.`risk_tier`,
    fp.`counterparty_name`,
    fp.`industry_group`,
    fp.`country_of_risk`,
    fp.`event_count`,
    fp.`distinct_event_count`,
    fp.`distinct_risk_tag_count`,
    fp.`risk_tag_set_size`,
    fp.`normalized_risk_tag_signature`,
    fp.`total_loss_amount`,
    fp.`total_exposure_amount`,
    fp.`max_severity_score`,
    fp.`avg_severity_score`,
    fp.`composite_risk_score`,
    fp.`risk_rank_per_account`,
    fp.`exposure_rank_per_jurisdiction`,
    fp.`regional_alert_family_exposure`,
    fp.`avg_severity_by_source_model`,
    fp.`loss_percentile_in_portfolio`,
    fp.`risk_band`,
    fp.`triage_action`,
    fp.`red_exposure_amount`,
    fp.`amber_exposure_amount`,
    fp.`yellow_exposure_amount`,
    fp.`green_exposure_amount`,
    fp.`cube_case_count`,
    fp.`cube_total_exposure_amount`,
    fp.`cube_total_loss_amount`,
    fp.`latest_event_ts_text`
FROM final_projection fp
WHERE fp.`risk_band` IN ('RED', 'AMBER', 'YELLOW');
