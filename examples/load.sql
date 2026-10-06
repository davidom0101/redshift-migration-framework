-- Run once against empty source and dimension tables.
-- Input: gzip CSV with a header, a unique event_id and UTC timestamps.
-- The original dataset needs event_id added before loading.
-- Columns: event_id,event_time,event_type,product_id,category_id,category_code,
--          brand,price,user_id,user_session
-- Replace the bucket name below.
COPY demo.fact_events_source
FROM 's3://YOUR-PROJECT-BUCKET/redshift-migration/source/events.csv.gz'
IAM_ROLE default
FORMAT AS CSV GZIP
IGNOREHEADER 1
TIMEFORMAT 'auto'
EMPTYASNULL
BLANKSASNULL;

INSERT INTO demo.dim_user
SELECT user_id, MIN(event_time), COUNT(*)
FROM demo.fact_events_source
WHERE user_id IS NOT NULL
GROUP BY user_id;

ANALYZE demo.fact_events_source;
ANALYZE demo.dim_user;

-- Check the load. Leave the target empty for the migration.
SELECT COUNT(*) AS source_rows, COUNT(DISTINCT event_id) AS unique_event_ids,
       MIN(event_time) AS first_event, MAX(event_time) AS last_event
FROM demo.fact_events_source;
SELECT COUNT(*) AS users FROM demo.dim_user;
SELECT COUNT(*) AS target_rows FROM demo.fact_events_rebuilt;

SELECT "schema", "table", diststyle, sortkey1, unsorted, skew_rows, tbl_rows, size
FROM svv_table_info
WHERE "schema" = 'demo'
ORDER BY "table";
