-- Run once in a new demo database.
CREATE SCHEMA IF NOT EXISTS demo;

-- Source keys are a poor fit for date filters and joins on user_id.
CREATE TABLE demo.fact_events_source
(
    event_id BIGINT NOT NULL,
    event_time TIMESTAMP,
    event_type VARCHAR(24),
    product_id BIGINT,
    category_id BIGINT,
    category_code VARCHAR(256),
    brand VARCHAR(128),
    price DECIMAL(12,2),
    user_id BIGINT,
    user_session VARCHAR(64)
)
DISTSTYLE KEY
DISTKEY (event_type)
COMPOUND SORTKEY (product_id);

-- Same columns, different physical keys. Benchmark against the source.
CREATE TABLE demo.fact_events_rebuilt
(
    event_id BIGINT NOT NULL,
    event_time TIMESTAMP,
    event_type VARCHAR(24),
    product_id BIGINT,
    category_id BIGINT,
    category_code VARCHAR(256),
    brand VARCHAR(128),
    price DECIMAL(12,2),
    user_id BIGINT,
    user_session VARCHAR(64)
)
DISTSTYLE KEY
DISTKEY (user_id)
COMPOUND SORTKEY (event_time);

-- User-level summary populated by load.sql.
CREATE TABLE demo.dim_user
(
    user_id BIGINT NOT NULL,
    first_seen_at TIMESTAMP,
    event_count BIGINT
)
DISTSTYLE KEY
DISTKEY (user_id)
SORTKEY (user_id);
