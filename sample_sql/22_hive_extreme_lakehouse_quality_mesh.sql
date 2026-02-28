-- Extreme Hive sample with semi-structured parsing, lateral views, windowing, and partition overwrite
WITH raw_ingest AS (
    SELECT
        i.`ingest_id`,
        i.`tenant_id`,
        i.`pipeline_name`,
        i.`source_system`,
        i.`landing_date`,
        i.`ingest_ts`,
        i.`record_count`,
        i.`error_count`,
        i.`warning_count`,
        i.`payload_json`,
        i.`quality_tags_csv`
    FROM `lakehouse_ingest_audit` i
    WHERE i.`landing_date` BETWEEN DATE '2025-10-01' AND DATE '2025-10-31'
),
parsed_payload AS (
    SELECT
        r.`ingest_id`,
        r.`tenant_id`,
        r.`pipeline_name`,
        r.`source_system`,
        r.`landing_date`,
        r.`ingest_ts`,
        r.`record_count`,
        r.`error_count`,
        r.`warning_count`,
        jt.`dataset_name`,
        jt.`load_mode`,
        jt.`owner_team`,
        jt.`storage_zone`,
        split(coalesce(r.`quality_tags_csv`, ''), ',') AS `quality_tags`
    FROM raw_ingest r
    LATERAL VIEW json_tuple(
        r.`payload_json`,
        'datasetName',
        'loadMode',
        'ownerTeam',
        'storageZone'
    ) jt AS `dataset_name`, `load_mode`, `owner_team`, `storage_zone`
),
exploded_quality_tags AS (
    SELECT
        p.`tenant_id`,
        p.`pipeline_name`,
        p.`source_system`,
        p.`landing_date`,
        p.`dataset_name`,
        p.`load_mode`,
        p.`owner_team`,
        p.`storage_zone`,
        p.`record_count`,
        p.`error_count`,
        p.`warning_count`,
        trim(qt.`quality_tag`) AS `quality_tag`
    FROM parsed_payload p
    LATERAL VIEW OUTER explode(p.`quality_tags`) qt AS `quality_tag`
),
dataset_day_rollup AS (
    SELECT
        e.`tenant_id`,
        e.`dataset_name`,
        e.`pipeline_name`,
        e.`source_system`,
        e.`owner_team`,
        e.`storage_zone`,
        e.`landing_date`,
        COUNT(*) AS `ingest_attempt_count`,
        SUM(e.`record_count`) AS `total_record_count`,
        SUM(e.`error_count`) AS `total_error_count`,
        SUM(e.`warning_count`) AS `total_warning_count`,
        COUNT(DISTINCT e.`quality_tag`) AS `distinct_quality_tag_count`,
        collect_set(e.`quality_tag`) AS `quality_tag_set`
    FROM exploded_quality_tags e
    GROUP BY
        e.`tenant_id`,
        e.`dataset_name`,
        e.`pipeline_name`,
        e.`source_system`,
        e.`owner_team`,
        e.`storage_zone`,
        e.`landing_date`
),
scored_datasets AS (
    SELECT
        ddr.`tenant_id`,
        ddr.`dataset_name`,
        ddr.`pipeline_name`,
        ddr.`source_system`,
        ddr.`owner_team`,
        ddr.`storage_zone`,
        ddr.`landing_date`,
        ddr.`ingest_attempt_count`,
        ddr.`total_record_count`,
        ddr.`total_error_count`,
        ddr.`total_warning_count`,
        ddr.`distinct_quality_tag_count`,
        size(ddr.`quality_tag_set`) AS `quality_tag_array_size`,
        CASE
            WHEN ddr.`total_record_count` = 0 THEN 0.0
            ELSE 1.0 - (cast(ddr.`total_error_count` AS double) / cast(ddr.`total_record_count` AS double))
        END AS `quality_score`,
        ROW_NUMBER() OVER (
            PARTITION BY ddr.`tenant_id`, ddr.`dataset_name`
            ORDER BY ddr.`landing_date` DESC, ddr.`total_record_count` DESC
        ) AS `recency_rank`,
        AVG(ddr.`total_error_count`) OVER (
            PARTITION BY ddr.`tenant_id`, ddr.`dataset_name`
        ) AS `avg_error_count_per_dataset`,
        MAX(ddr.`total_warning_count`) OVER (
            PARTITION BY ddr.`tenant_id`, ddr.`dataset_name`
        ) AS `max_warning_count_per_dataset`
    FROM dataset_day_rollup ddr
),
quality_alerts AS (
    SELECT
        sd.`tenant_id`,
        sd.`dataset_name`,
        sd.`pipeline_name`,
        sd.`source_system`,
        sd.`owner_team`,
        sd.`storage_zone`,
        sd.`landing_date`,
        sd.`quality_score`,
        sd.`total_error_count`,
        sd.`total_warning_count`,
        CASE
            WHEN sd.`quality_score` < 0.950 THEN 'CRITICAL'
            WHEN sd.`quality_score` < 0.985 THEN 'HIGH'
            WHEN sd.`total_warning_count` > sd.`max_warning_count_per_dataset` * 0.8 THEN 'ELEVATED'
            ELSE 'NORMAL'
        END AS `alert_severity`,
        percentile_approx(sd.`total_record_count`, 0.5) OVER (
            PARTITION BY sd.`tenant_id`, sd.`source_system`
        ) AS `median_record_count_by_source`
    FROM scored_datasets sd
    WHERE sd.`recency_rank` <= 3
)
INSERT OVERWRITE TABLE `analytics`.`lakehouse_quality_mesh`
PARTITION (`snapshot_month` = '2025-10')
SELECT
    qa.`tenant_id`,
    qa.`dataset_name`,
    qa.`pipeline_name`,
    qa.`source_system`,
    qa.`owner_team`,
    qa.`storage_zone`,
    qa.`landing_date`,
    qa.`quality_score`,
    qa.`total_error_count`,
    qa.`total_warning_count`,
    qa.`median_record_count_by_source`,
    qa.`alert_severity`,
    CASE
        WHEN qa.`alert_severity` IN ('CRITICAL', 'HIGH') THEN 1
        ELSE 0
    END AS `requires_escalation`
FROM quality_alerts qa
WHERE qa.`alert_severity` <> 'NORMAL';
