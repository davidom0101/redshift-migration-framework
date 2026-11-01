-- Run once for a new migration after checking the source is stable and the target is empty.
-- Rerunning inserts duplicate chunks, skip this script when resuming.
INSERT INTO ops.migration_chunks
(
    migration_id, chunk_id, source_schema, source_table,
    target_schema, target_table, timestamp_column, chunk_start, chunk_end
)
VALUES
    ('ecommerce-events-october-demo', 1,
     'demo', 'fact_events_source', 'demo', 'fact_events_rebuilt',
     'event_time', '2019-10-01', '2019-10-08'),

    ('ecommerce-events-october-demo', 2,
     'demo', 'fact_events_source', 'demo', 'fact_events_rebuilt',
     'event_time', '2019-10-08', '2019-10-15'),

    ('ecommerce-events-october-demo', 3,
     'demo', 'fact_events_source', 'demo', 'fact_events_rebuilt',
     'event_time', '2019-10-15', '2019-10-22'),

    ('ecommerce-events-october-demo', 4,
     'demo', 'fact_events_source', 'demo', 'fact_events_rebuilt',
     'event_time', '2019-10-22', '2019-10-29'),

    ('ecommerce-events-october-demo', 5,
     'demo', 'fact_events_source', 'demo', 'fact_events_rebuilt',
     'event_time', '2019-10-29', '2019-11-01');
