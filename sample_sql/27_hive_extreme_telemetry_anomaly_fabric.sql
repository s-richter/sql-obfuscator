-- Extreme Hive sample with semi-structured telemetry extraction, sessionized rollups,
-- sequence-aware window logic, grouping sets, and partitioned insert overwrite
WITH raw_device_events AS (
    SELECT
        e.`telemetry_event_id`,
        e.`device_id`,
        e.`fleet_id`,
        e.`site_id`,
        e.`region_code`,
        e.`firmware_version`,
        e.`event_ts`,
        e.`event_date`,
        e.`event_type`,
        e.`event_status`,
        e.`temperature_celsius`,
        e.`vibration_score`,
        e.`power_draw_kw`,
        e.`payload_json`,
        e.`sensor_flags_csv`
    FROM `iot_device_telemetry_events` e
    WHERE e.`event_date` BETWEEN DATE '2025-09-01' AND DATE '2025-12-31'
      AND e.`event_status` IN ('OK', 'WARN', 'ERROR')
),
payload_projection AS (
    SELECT
        r.`telemetry_event_id`,
        r.`device_id`,
        r.`fleet_id`,
        r.`site_id`,
        r.`region_code`,
        r.`firmware_version`,
        r.`event_ts`,
        r.`event_date`,
        r.`event_type`,
        r.`event_status`,
        r.`temperature_celsius`,
        r.`vibration_score`,
        r.`power_draw_kw`,
        jt.`device_mode`,
        jt.`component_name`,
        jt.`maintenance_state`,
        jt.`anomaly_family`,
        split(coalesce(r.`sensor_flags_csv`, ''), ',') AS `sensor_flag_array`
    FROM raw_device_events r
    LATERAL VIEW json_tuple(
        r.`payload_json`,
        'deviceMode',
        'componentName',
        'maintenanceState',
        'anomalyFamily'
    ) jt AS `device_mode`, `component_name`, `maintenance_state`, `anomaly_family`
),
exploded_sensor_flags AS (
    SELECT
        pp.`telemetry_event_id`,
        pp.`device_id`,
        pp.`fleet_id`,
        pp.`site_id`,
        pp.`region_code`,
        pp.`firmware_version`,
        pp.`event_ts`,
        pp.`event_date`,
        pp.`event_type`,
        pp.`event_status`,
        pp.`temperature_celsius`,
        pp.`vibration_score`,
        pp.`power_draw_kw`,
        pp.`device_mode`,
        pp.`component_name`,
        pp.`maintenance_state`,
        pp.`anomaly_family`,
        trim(sf.`sensor_flag`) AS `sensor_flag`
    FROM payload_projection pp
    LATERAL VIEW OUTER explode(pp.`sensor_flag_array`) sf AS `sensor_flag`
),
ordered_device_events AS (
    SELECT
        esf.`telemetry_event_id`,
        esf.`device_id`,
        esf.`fleet_id`,
        esf.`site_id`,
        esf.`region_code`,
        esf.`firmware_version`,
        esf.`event_ts`,
        esf.`event_date`,
        esf.`event_type`,
        esf.`event_status`,
        esf.`temperature_celsius`,
        esf.`vibration_score`,
        esf.`power_draw_kw`,
        esf.`device_mode`,
        esf.`component_name`,
        esf.`maintenance_state`,
        esf.`anomaly_family`,
        esf.`sensor_flag`,
        lag(esf.`event_ts`) OVER (
            PARTITION BY esf.`device_id`
            ORDER BY esf.`event_ts`, esf.`telemetry_event_id`
        ) AS `prev_event_ts`,
        lag(esf.`temperature_celsius`) OVER (
            PARTITION BY esf.`device_id`
            ORDER BY esf.`event_ts`, esf.`telemetry_event_id`
        ) AS `prev_temperature_celsius`,
        lag(esf.`power_draw_kw`) OVER (
            PARTITION BY esf.`device_id`
            ORDER BY esf.`event_ts`, esf.`telemetry_event_id`
        ) AS `prev_power_draw_kw`
    FROM exploded_sensor_flags esf
),
sessionized_events AS (
    SELECT
        ode.`telemetry_event_id`,
        ode.`device_id`,
        ode.`fleet_id`,
        ode.`site_id`,
        ode.`region_code`,
        ode.`firmware_version`,
        ode.`event_ts`,
        ode.`event_date`,
        ode.`event_type`,
        ode.`event_status`,
        ode.`temperature_celsius`,
        ode.`vibration_score`,
        ode.`power_draw_kw`,
        ode.`device_mode`,
        ode.`component_name`,
        ode.`maintenance_state`,
        ode.`anomaly_family`,
        ode.`sensor_flag`,
        unix_timestamp(ode.`event_ts`) - unix_timestamp(ode.`prev_event_ts`) AS `seconds_since_prev_event`,
        CASE
            WHEN ode.`prev_event_ts` IS NULL THEN 1
            WHEN unix_timestamp(ode.`event_ts`) - unix_timestamp(ode.`prev_event_ts`) > 1800 THEN 1
            ELSE 0
        END AS `new_session_marker`,
        coalesce(ode.`temperature_celsius`, 0.0) - coalesce(ode.`prev_temperature_celsius`, 0.0) AS `temperature_delta`,
        coalesce(ode.`power_draw_kw`, 0.0) - coalesce(ode.`prev_power_draw_kw`, 0.0) AS `power_delta`
    FROM ordered_device_events ode
),
session_keys AS (
    SELECT
        se.`telemetry_event_id`,
        se.`device_id`,
        se.`fleet_id`,
        se.`site_id`,
        se.`region_code`,
        se.`firmware_version`,
        se.`event_ts`,
        se.`event_date`,
        se.`event_type`,
        se.`event_status`,
        se.`temperature_celsius`,
        se.`vibration_score`,
        se.`power_draw_kw`,
        se.`device_mode`,
        se.`component_name`,
        se.`maintenance_state`,
        se.`anomaly_family`,
        se.`sensor_flag`,
        se.`seconds_since_prev_event`,
        se.`new_session_marker`,
        se.`temperature_delta`,
        se.`power_delta`,
        sum(se.`new_session_marker`) OVER (
            PARTITION BY se.`device_id`
            ORDER BY se.`event_ts`, se.`telemetry_event_id`
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS `session_sequence_id`
    FROM sessionized_events se
),
session_rollup AS (
    SELECT
        sk.`device_id`,
        sk.`fleet_id`,
        sk.`site_id`,
        sk.`region_code`,
        sk.`firmware_version`,
        sk.`device_mode`,
        sk.`component_name`,
        sk.`maintenance_state`,
        sk.`anomaly_family`,
        sk.`session_sequence_id`,
        MIN(sk.`event_ts`) AS `session_start_ts`,
        MAX(sk.`event_ts`) AS `session_end_ts`,
        COUNT(*) AS `session_event_count`,
        COUNT(DISTINCT sk.`telemetry_event_id`) AS `distinct_event_count`,
        COUNT(DISTINCT sk.`sensor_flag`) AS `distinct_sensor_flag_count`,
        collect_set(sk.`sensor_flag`) AS `sensor_flag_set`,
        AVG(sk.`temperature_celsius`) AS `avg_temperature_celsius`,
        MAX(sk.`temperature_celsius`) AS `max_temperature_celsius`,
        AVG(sk.`vibration_score`) AS `avg_vibration_score`,
        MAX(sk.`vibration_score`) AS `max_vibration_score`,
        AVG(sk.`power_draw_kw`) AS `avg_power_draw_kw`,
        MAX(sk.`power_draw_kw`) AS `max_power_draw_kw`,
        SUM(CASE WHEN sk.`event_status` = 'ERROR' THEN 1 ELSE 0 END) AS `error_event_count`,
        SUM(CASE WHEN sk.`event_status` = 'WARN' THEN 1 ELSE 0 END) AS `warn_event_count`,
        MAX(abs(sk.`temperature_delta`)) AS `max_temperature_delta`,
        MAX(abs(sk.`power_delta`)) AS `max_power_delta`
    FROM session_keys sk
    GROUP BY
        sk.`device_id`,
        sk.`fleet_id`,
        sk.`site_id`,
        sk.`region_code`,
        sk.`firmware_version`,
        sk.`device_mode`,
        sk.`component_name`,
        sk.`maintenance_state`,
        sk.`anomaly_family`,
        sk.`session_sequence_id`
),
device_baseline AS (
    SELECT
        d.`device_id`,
        d.`device_model`,
        d.`device_generation`,
        d.`criticality_tier`,
        d.`commissioned_date`,
        d.`asset_owner_team`
    FROM `device_asset_baseline` d
    WHERE d.`is_current` = 1
),
site_baseline AS (
    SELECT
        s.`site_id`,
        s.`site_name`,
        s.`site_type`,
        s.`grid_zone`,
        s.`country_code`
    FROM `industrial_site_baseline` s
    WHERE s.`snapshot_date` = DATE '2025-12-31'
),
joined_sessions AS (
    SELECT
        sr.`device_id`,
        sr.`fleet_id`,
        sr.`site_id`,
        sr.`region_code`,
        sr.`firmware_version`,
        sr.`device_mode`,
        sr.`component_name`,
        sr.`maintenance_state`,
        sr.`anomaly_family`,
        sr.`session_sequence_id`,
        sr.`session_start_ts`,
        sr.`session_end_ts`,
        sr.`session_event_count`,
        sr.`distinct_event_count`,
        sr.`distinct_sensor_flag_count`,
        size(sr.`sensor_flag_set`) AS `sensor_flag_set_size`,
        concat_ws('|', sort_array(sr.`sensor_flag_set`)) AS `normalized_sensor_flag_signature`,
        sr.`avg_temperature_celsius`,
        sr.`max_temperature_celsius`,
        sr.`avg_vibration_score`,
        sr.`max_vibration_score`,
        sr.`avg_power_draw_kw`,
        sr.`max_power_draw_kw`,
        sr.`error_event_count`,
        sr.`warn_event_count`,
        sr.`max_temperature_delta`,
        sr.`max_power_delta`,
        db.`device_model`,
        db.`device_generation`,
        db.`criticality_tier`,
        db.`commissioned_date`,
        db.`asset_owner_team`,
        sb.`site_name`,
        sb.`site_type`,
        sb.`grid_zone`,
        sb.`country_code`
    FROM session_rollup sr
    LEFT JOIN device_baseline db
        ON sr.`device_id` = db.`device_id`
    LEFT JOIN site_baseline sb
        ON sr.`site_id` = sb.`site_id`
),
scored_sessions AS (
    SELECT
        js.`device_id`,
        js.`fleet_id`,
        js.`site_id`,
        js.`region_code`,
        js.`firmware_version`,
        js.`device_mode`,
        js.`component_name`,
        js.`maintenance_state`,
        js.`anomaly_family`,
        js.`session_sequence_id`,
        js.`session_start_ts`,
        js.`session_end_ts`,
        js.`session_event_count`,
        js.`distinct_event_count`,
        js.`distinct_sensor_flag_count`,
        js.`sensor_flag_set_size`,
        js.`normalized_sensor_flag_signature`,
        js.`avg_temperature_celsius`,
        js.`max_temperature_celsius`,
        js.`avg_vibration_score`,
        js.`max_vibration_score`,
        js.`avg_power_draw_kw`,
        js.`max_power_draw_kw`,
        js.`error_event_count`,
        js.`warn_event_count`,
        js.`max_temperature_delta`,
        js.`max_power_delta`,
        js.`device_model`,
        js.`device_generation`,
        js.`criticality_tier`,
        js.`commissioned_date`,
        js.`asset_owner_team`,
        js.`site_name`,
        js.`site_type`,
        js.`grid_zone`,
        js.`country_code`,
        (
            js.`max_temperature_celsius` * 0.35
            + js.`max_vibration_score` * 12.0
            + js.`max_power_delta` * 4.0
            + js.`error_event_count` * 10.0
            + js.`warn_event_count` * 4.0
            + CASE WHEN js.`criticality_tier` = 'TIER_1' THEN 25.0 ELSE 0.0 END
            + CASE WHEN js.`maintenance_state` = 'OVERDUE' THEN 18.0 ELSE 0.0 END
        ) AS `composite_anomaly_score`,
        row_number() OVER (
            PARTITION BY js.`device_id`
            ORDER BY js.`session_start_ts` DESC, js.`session_sequence_id` DESC
        ) AS `session_recency_rank`,
        dense_rank() OVER (
            PARTITION BY js.`site_id`
            ORDER BY js.`max_vibration_score` DESC, js.`session_sequence_id`
        ) AS `site_vibration_rank`,
        sum(js.`error_event_count`) OVER (
            PARTITION BY js.`grid_zone`, js.`component_name`
        ) AS `grid_component_error_total`,
        avg(js.`max_temperature_celsius`) OVER (
            PARTITION BY js.`device_generation`
        ) AS `avg_peak_temperature_by_generation`,
        percent_rank() OVER (
            PARTITION BY js.`fleet_id`
            ORDER BY js.`max_power_draw_kw`
        ) AS `power_draw_percentile_in_fleet`
    FROM joined_sessions js
),
classified_sessions AS (
    SELECT
        ss.`device_id`,
        ss.`fleet_id`,
        ss.`site_id`,
        ss.`region_code`,
        ss.`firmware_version`,
        ss.`device_mode`,
        ss.`component_name`,
        ss.`maintenance_state`,
        ss.`anomaly_family`,
        ss.`session_sequence_id`,
        ss.`session_start_ts`,
        ss.`session_end_ts`,
        ss.`session_event_count`,
        ss.`distinct_event_count`,
        ss.`distinct_sensor_flag_count`,
        ss.`sensor_flag_set_size`,
        ss.`normalized_sensor_flag_signature`,
        ss.`avg_temperature_celsius`,
        ss.`max_temperature_celsius`,
        ss.`avg_vibration_score`,
        ss.`max_vibration_score`,
        ss.`avg_power_draw_kw`,
        ss.`max_power_draw_kw`,
        ss.`error_event_count`,
        ss.`warn_event_count`,
        ss.`max_temperature_delta`,
        ss.`max_power_delta`,
        ss.`device_model`,
        ss.`device_generation`,
        ss.`criticality_tier`,
        ss.`commissioned_date`,
        ss.`asset_owner_team`,
        ss.`site_name`,
        ss.`site_type`,
        ss.`grid_zone`,
        ss.`country_code`,
        ss.`composite_anomaly_score`,
        ss.`session_recency_rank`,
        ss.`site_vibration_rank`,
        ss.`grid_component_error_total`,
        ss.`avg_peak_temperature_by_generation`,
        ss.`power_draw_percentile_in_fleet`,
        CASE
            WHEN ss.`composite_anomaly_score` >= 180 THEN 'CRITICAL'
            WHEN ss.`composite_anomaly_score` >= 120 THEN 'HIGH'
            WHEN ss.`composite_anomaly_score` >= 75 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS `anomaly_band`,
        CASE
            WHEN ss.`criticality_tier` = 'TIER_1' AND ss.`composite_anomaly_score` >= 120 THEN 'IMMEDIATE_DISPATCH'
            WHEN ss.`session_recency_rank` = 1 AND ss.`composite_anomaly_score` >= 100 THEN 'RECENT_HIGH_RISK_REVIEW'
            WHEN ss.`power_draw_percentile_in_fleet` >= 0.95 THEN 'POWER_SPIKE_REVIEW'
            ELSE 'STANDARD_OBSERVATION'
        END AS `recommended_response`
    FROM scored_sessions ss
),
cube_summary AS (
    SELECT
        coalesce(cs.`grid_zone`, 'ALL_GRID_ZONES') AS `grid_zone`,
        coalesce(cs.`component_name`, 'ALL_COMPONENTS') AS `component_name`,
        coalesce(cs.`anomaly_band`, 'ALL_BANDS') AS `anomaly_band`,
        COUNT(DISTINCT cs.`device_id`) AS `cube_device_count`,
        COUNT(*) AS `cube_session_count`,
        SUM(cs.`error_event_count`) AS `cube_error_event_count`
    FROM classified_sessions cs
    GROUP BY GROUPING SETS (
        (cs.`grid_zone`, cs.`component_name`, cs.`anomaly_band`),
        (cs.`grid_zone`, cs.`component_name`),
        (cs.`grid_zone`),
        ()
    )
),
band_pivot AS (
    SELECT
        cs.`fleet_id`,
        cs.`grid_zone`,
        SUM(CASE WHEN cs.`anomaly_band` = 'CRITICAL' THEN cs.`max_power_draw_kw` ELSE 0.0 END) AS `critical_peak_power_kw`,
        SUM(CASE WHEN cs.`anomaly_band` = 'HIGH' THEN cs.`max_power_draw_kw` ELSE 0.0 END) AS `high_peak_power_kw`,
        SUM(CASE WHEN cs.`anomaly_band` = 'MEDIUM' THEN cs.`max_power_draw_kw` ELSE 0.0 END) AS `medium_peak_power_kw`,
        SUM(CASE WHEN cs.`anomaly_band` = 'LOW' THEN cs.`max_power_draw_kw` ELSE 0.0 END) AS `low_peak_power_kw`
    FROM classified_sessions cs
    GROUP BY
        cs.`fleet_id`,
        cs.`grid_zone`
),
final_projection AS (
    SELECT
        cs.`device_id`,
        cs.`fleet_id`,
        cs.`site_id`,
        cs.`region_code`,
        cs.`firmware_version`,
        cs.`device_mode`,
        cs.`component_name`,
        cs.`maintenance_state`,
        cs.`anomaly_family`,
        cs.`session_sequence_id`,
        cs.`session_start_ts`,
        cs.`session_end_ts`,
        cs.`session_event_count`,
        cs.`distinct_event_count`,
        cs.`distinct_sensor_flag_count`,
        cs.`sensor_flag_set_size`,
        cs.`normalized_sensor_flag_signature`,
        cs.`avg_temperature_celsius`,
        cs.`max_temperature_celsius`,
        cs.`avg_vibration_score`,
        cs.`max_vibration_score`,
        cs.`avg_power_draw_kw`,
        cs.`max_power_draw_kw`,
        cs.`error_event_count`,
        cs.`warn_event_count`,
        cs.`max_temperature_delta`,
        cs.`max_power_delta`,
        cs.`device_model`,
        cs.`device_generation`,
        cs.`criticality_tier`,
        cs.`commissioned_date`,
        cs.`asset_owner_team`,
        cs.`site_name`,
        cs.`site_type`,
        cs.`grid_zone`,
        cs.`country_code`,
        cs.`composite_anomaly_score`,
        cs.`session_recency_rank`,
        cs.`site_vibration_rank`,
        cs.`grid_component_error_total`,
        cs.`avg_peak_temperature_by_generation`,
        cs.`power_draw_percentile_in_fleet`,
        cs.`anomaly_band`,
        cs.`recommended_response`,
        bp.`critical_peak_power_kw`,
        bp.`high_peak_power_kw`,
        bp.`medium_peak_power_kw`,
        bp.`low_peak_power_kw`,
        cu.`cube_device_count`,
        cu.`cube_session_count`,
        cu.`cube_error_event_count`,
        date_format(cs.`session_end_ts`, 'yyyy-MM-dd HH:mm:ss') AS `session_end_ts_text`
    FROM classified_sessions cs
    LEFT JOIN band_pivot bp
        ON cs.`fleet_id` = bp.`fleet_id`
       AND cs.`grid_zone` = bp.`grid_zone`
    LEFT JOIN cube_summary cu
        ON cs.`grid_zone` = cu.`grid_zone`
       AND cs.`component_name` = cu.`component_name`
       AND cs.`anomaly_band` = cu.`anomaly_band`
)
INSERT OVERWRITE TABLE `analytics`.`telemetry_anomaly_fabric`
PARTITION (`snapshot_month` = '2025-12')
SELECT
    fp.`device_id`,
    fp.`fleet_id`,
    fp.`site_id`,
    fp.`region_code`,
    fp.`firmware_version`,
    fp.`device_mode`,
    fp.`component_name`,
    fp.`maintenance_state`,
    fp.`anomaly_family`,
    fp.`session_sequence_id`,
    fp.`session_start_ts`,
    fp.`session_end_ts`,
    fp.`session_event_count`,
    fp.`distinct_event_count`,
    fp.`distinct_sensor_flag_count`,
    fp.`sensor_flag_set_size`,
    fp.`normalized_sensor_flag_signature`,
    fp.`avg_temperature_celsius`,
    fp.`max_temperature_celsius`,
    fp.`avg_vibration_score`,
    fp.`max_vibration_score`,
    fp.`avg_power_draw_kw`,
    fp.`max_power_draw_kw`,
    fp.`error_event_count`,
    fp.`warn_event_count`,
    fp.`max_temperature_delta`,
    fp.`max_power_delta`,
    fp.`device_model`,
    fp.`device_generation`,
    fp.`criticality_tier`,
    fp.`commissioned_date`,
    fp.`asset_owner_team`,
    fp.`site_name`,
    fp.`site_type`,
    fp.`grid_zone`,
    fp.`country_code`,
    fp.`composite_anomaly_score`,
    fp.`session_recency_rank`,
    fp.`site_vibration_rank`,
    fp.`grid_component_error_total`,
    fp.`avg_peak_temperature_by_generation`,
    fp.`power_draw_percentile_in_fleet`,
    fp.`anomaly_band`,
    fp.`recommended_response`,
    fp.`critical_peak_power_kw`,
    fp.`high_peak_power_kw`,
    fp.`medium_peak_power_kw`,
    fp.`low_peak_power_kw`,
    fp.`cube_device_count`,
    fp.`cube_session_count`,
    fp.`cube_error_event_count`,
    fp.`session_end_ts_text`
FROM final_projection fp
WHERE fp.`anomaly_band` IN ('CRITICAL', 'HIGH', 'MEDIUM');
