-- Table definitions with storage clauses. SerDe and format class names are not secrets;
-- locations and table properties are.
CREATE DATABASE IF NOT EXISTS lake_raw COMMENT 'landing zone' LOCATION 's3a://corp-lake-prod/raw/';

CREATE EXTERNAL TABLE IF NOT EXISTS lake_raw.click_events (
    event_id      STRING COMMENT 'unique id from the tracker',
    visitor_id    BIGINT,
    page_url      STRING,
    properties    MAP<STRING, STRING>,
    items         ARRAY<STRUCT<sku: STRING, qty: INT, price: DECIMAL(12, 2)>>,
    received_at   TIMESTAMP
)
COMMENT 'Raw click stream'
PARTITIONED BY (event_date STRING, region STRING)
CLUSTERED BY (visitor_id) SORTED BY (received_at ASC) INTO 32 BUCKETS
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
          OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3a://corp-lake-prod/raw/click_events/'
TBLPROPERTIES ('owner.team' = 'web-analytics', 'retention.days' = '400');

CREATE TABLE lake_curated.daily_visits (
    visitor_id BIGINT,
    visits     INT,
    revenue    DECIMAL(18, 2)
)
PARTITIONED BY (event_date STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n'
STORED AS ORC
TBLPROPERTIES ('orc.compress' = 'SNAPPY');

CREATE TABLE lake_curated.visits_parquet STORED AS PARQUET AS
SELECT visitor_id, visits FROM lake_curated.daily_visits WHERE event_date = '2024-06-30';

ALTER TABLE lake_raw.click_events ADD IF NOT EXISTS PARTITION (event_date = '2024-07-01', region = 'eu')
    LOCATION 's3a://corp-lake-prod/raw/click_events/2024-07-01/eu/';
ALTER TABLE lake_curated.daily_visits SET TBLPROPERTIES ('comment' = 'rebuilt nightly');
DROP TABLE IF EXISTS lake_curated.visits_tmp PURGE;
