-- New environments only. Review existing tables before changing their schema.
CREATE SCHEMA IF NOT EXISTS ops;

-- One row per (migration_id, chunk_id); Redshift does not enforce uniqueness.
CREATE TABLE ops.migration_chunks
(
    migration_id VARCHAR(100) NOT NULL,
    chunk_id INTEGER NOT NULL,
    source_schema VARCHAR(127) NOT NULL,
    source_table VARCHAR(127) NOT NULL,
    target_schema VARCHAR(127) NOT NULL,
    target_table VARCHAR(127) NOT NULL,
    timestamp_column VARCHAR(127) NOT NULL,
    chunk_start TIMESTAMP NOT NULL,
    chunk_end TIMESTAMP NOT NULL,
    status VARCHAR(16) DEFAULT 'PENDING' NOT NULL,
    source_count BIGINT,
    target_count BIGINT,
    completed_at TIMESTAMP
)
DISTSTYLE EVEN;
