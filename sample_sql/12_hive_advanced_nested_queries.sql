-- Advanced Hive sample with chained CTEs, subqueries, joins, and set operations
WITH active_sessions AS (
    SELECT
        s.`session_id`,
        s.`user_id`,
        s.`device_id`,
        s.`session_start_ts`,
        s.`session_end_ts`,
        s.`traffic_source`
    FROM `app_sessions` s
    WHERE s.`session_start_ts` >= TIMESTAMP '2025-06-01 00:00:00'
      AND s.`traffic_source` <> 'internal'
),
event_rollup AS (
    SELECT
        e.`session_id`,
        COUNT(*) AS `event_count`,
        SUM(CASE WHEN e.`event_type` = 'purchase' THEN 1 ELSE 0 END) AS `purchase_event_count`,
        MAX(e.`event_ts`) AS `last_event_ts`
    FROM `app_events` e
    WHERE e.`session_id` IN (
        SELECT a.`session_id`
        FROM active_sessions a
    )
    GROUP BY e.`session_id`
),
qualified_sessions AS (
    SELECT
        a.`session_id`,
        a.`user_id`,
        a.`device_id`,
        a.`session_start_ts`,
        a.`session_end_ts`,
        a.`traffic_source`,
        er.`event_count`,
        er.`purchase_event_count`,
        er.`last_event_ts`
    FROM active_sessions a
    INNER JOIN event_rollup er
        ON a.`session_id` = er.`session_id`
    WHERE er.`event_count` >= 3
),
session_labels AS (
    SELECT
        qs.`session_id`,
        qs.`user_id`,
        qs.`device_id`,
        qs.`traffic_source`,
        qs.`event_count`,
        qs.`purchase_event_count`,
        CASE
            WHEN qs.`purchase_event_count` > 0 THEN 'BUYER'
            WHEN qs.`event_count` >= 10 THEN 'ENGAGED'
            ELSE 'BROWSER'
        END AS `session_label`
    FROM qualified_sessions qs
)
SELECT
    u.`user_name`,
    d.`device_type`,
    sl.`traffic_source`,
    sl.`event_count`,
    sl.`purchase_event_count`,
    sl.`session_label`
FROM session_labels sl
LEFT JOIN `dim_user` u
    ON sl.`user_id` = u.`user_id`
LEFT JOIN `dim_device` d
    ON sl.`device_id` = d.`device_id`
WHERE sl.`user_id` NOT IN (
    SELECT ex.`user_id`
    FROM `user_exclusion_list` ex
    WHERE ex.`is_active` = 1
)

UNION ALL

SELECT
    u.`user_name`,
    d.`device_type`,
    'reactivation' AS `traffic_source`,
    sl.`event_count`,
    sl.`purchase_event_count`,
    'REENGAGED' AS `session_label`
FROM session_labels sl
INNER JOIN `campaign_reactivation` cr
    ON sl.`user_id` = cr.`user_id`
LEFT JOIN `dim_user` u
    ON sl.`user_id` = u.`user_id`
LEFT JOIN `dim_device` d
    ON sl.`device_id` = d.`device_id`
WHERE cr.`campaign_date` = (
    SELECT MAX(cr2.`campaign_date`)
    FROM `campaign_reactivation` cr2
    WHERE cr2.`user_id` = cr.`user_id`
);
