-- Extreme Hive sample with path explosion, attribution weighting, windows, and unioned campaign outputs
WITH eligible_sessions AS (
    SELECT
        s.`session_id`,
        s.`user_id`,
        s.`journey_id`,
        s.`session_start_ts`,
        s.`session_end_ts`,
        s.`conversion_ts`,
        s.`gross_revenue`,
        s.`channel_path`,
        s.`country_code`,
        s.`device_family`
    FROM `journey_sessions` s
    WHERE s.`session_start_ts` >= TIMESTAMP '2025-09-01 00:00:00'
      AND s.`conversion_ts` IS NOT NULL
),
exploded_touchpoints AS (
    SELECT
        es.`session_id`,
        es.`user_id`,
        es.`journey_id`,
        es.`gross_revenue`,
        es.`country_code`,
        es.`device_family`,
        tp.`touch_index`,
        trim(tp.`touch_channel`) AS `touch_channel`
    FROM eligible_sessions es
    LATERAL VIEW posexplode(split(es.`channel_path`, '>')) tp AS `touch_index`, `touch_channel`
),
touchpoint_weights AS (
    SELECT
        et.`session_id`,
        et.`user_id`,
        et.`journey_id`,
        et.`gross_revenue`,
        et.`country_code`,
        et.`device_family`,
        et.`touch_index`,
        et.`touch_channel`,
        COUNT(*) OVER (
            PARTITION BY et.`session_id`
        ) AS `touch_count`,
        CASE
            WHEN et.`touch_index` = 0 THEN 0.40
            WHEN et.`touch_index` = COUNT(*) OVER (PARTITION BY et.`session_id`) - 1 THEN 0.40
            ELSE 0.20 / greatest(COUNT(*) OVER (PARTITION BY et.`session_id`) - 2, 1)
        END AS `attribution_weight`
    FROM exploded_touchpoints et
),
channel_attribution AS (
    SELECT
        tw.`country_code`,
        tw.`device_family`,
        tw.`touch_channel`,
        COUNT(DISTINCT tw.`session_id`) AS `attributed_session_count`,
        SUM(tw.`gross_revenue` * tw.`attribution_weight`) AS `attributed_revenue`,
        AVG(tw.`touch_count`) AS `avg_touch_count`,
        DENSE_RANK() OVER (
            PARTITION BY tw.`country_code`
            ORDER BY SUM(tw.`gross_revenue` * tw.`attribution_weight`) DESC, tw.`touch_channel`
        ) AS `revenue_rank_in_country`
    FROM touchpoint_weights tw
    GROUP BY
        tw.`country_code`,
        tw.`device_family`,
        tw.`touch_channel`
),
journey_profiles AS (
    SELECT
        es.`journey_id`,
        es.`user_id`,
        es.`country_code`,
        es.`device_family`,
        COUNT(DISTINCT et.`touch_channel`) AS `distinct_channel_count`,
        concat_ws(' > ', sort_array(collect_set(et.`touch_channel`))) AS `normalized_channel_set`,
        SUM(es.`gross_revenue`) AS `journey_revenue`,
        MAX(es.`conversion_ts`) AS `latest_conversion_ts`
    FROM eligible_sessions es
    INNER JOIN exploded_touchpoints et
        ON es.`session_id` = et.`session_id`
    GROUP BY
        es.`journey_id`,
        es.`user_id`,
        es.`country_code`,
        es.`device_family`
),
ranked_profiles AS (
    SELECT
        jp.`journey_id`,
        jp.`user_id`,
        jp.`country_code`,
        jp.`device_family`,
        jp.`distinct_channel_count`,
        jp.`normalized_channel_set`,
        jp.`journey_revenue`,
        jp.`latest_conversion_ts`,
        NTILE(5) OVER (
            PARTITION BY jp.`country_code`
            ORDER BY jp.`journey_revenue` DESC
        ) AS `revenue_quintile`,
        ROW_NUMBER() OVER (
            PARTITION BY jp.`country_code`, jp.`device_family`
            ORDER BY jp.`journey_revenue` DESC, jp.`latest_conversion_ts` DESC
        ) AS `device_rank`
    FROM journey_profiles jp
)
SELECT
    ca.`country_code`,
    ca.`device_family`,
    ca.`touch_channel` AS `entity_name`,
    ca.`attributed_session_count` AS `session_count`,
    ca.`attributed_revenue` AS `revenue_value`,
    ca.`avg_touch_count` AS `support_metric`,
    'CHANNEL' AS `entity_type`
FROM channel_attribution ca
WHERE ca.`revenue_rank_in_country` <= 5

UNION ALL

SELECT
    rp.`country_code`,
    rp.`device_family`,
    rp.`normalized_channel_set` AS `entity_name`,
    rp.`distinct_channel_count` AS `session_count`,
    rp.`journey_revenue` AS `revenue_value`,
    cast(rp.`revenue_quintile` AS double) AS `support_metric`,
    'JOURNEY_PATTERN' AS `entity_type`
FROM ranked_profiles rp
WHERE rp.`device_rank` <= 10;
