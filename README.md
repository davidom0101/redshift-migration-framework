# Redshift chunked deep copy

Rebuild a Redshift table with different sort or distribution keys. One Python runner
copies date chunks sequentially through the Data API and records progress in
`ops.migration_chunks` so completed chunks can be skipped on restart.

## Run

Requires Python 3.13, uv, AWS credentials and Data API access. For optional infrastructure
setup, see /infrastructure/terraform/README.md.

Create an empty target with matching logical columns and your chosen keys. From the
project root, copy the template and edit the connection, tables and chunk ranges:

```bash
uv sync --locked
cp examples/migration.yaml migration.yaml
# Edit migration.yaml before continuing.
uv run python -m migration.setup --config migration.yaml
uv run python -m migration.runner --config migration.yaml
```

Use `workgroup` for Serverless or `cluster_identifier` for provisioned Redshift.
Supply a database secret ARN in YAML; AWS credentials come from the usual credential chain.

Setup creates missing control objects and seeds the chunks once. An identical rerun
preserves progress. Setup refuses an incompatible control table, and both commands
refuse a YAML plan that differs from the stored chunks.

## Stop and resume

Add `--max-chunks 1` to stop after one newly copied and checked chunk. Resume with the
original run command and YAML. The runner rechecks DONE chunks before copying pending
ones. Copy and DONE commit together; a later count failure leaves the chunk DONE.

## Operating limits

- Use one operator and runner. Pause source writes and prevent other target writers.
- Date chunks suit a compound sort key with the date column first, such as
  `COMPOUND SORTKEY (event_time)`. Use contiguous UTC ranges covering all rows,
  with inclusive starts and exclusive ends. NULL dates are refused.
- `wait_timeout_seconds` defaults to 3,600 per statement. A timeout stops polling;
  the SQL may still be running. Inspect its outcome before retrying. There are no automatic retries.
- Matching counts do not prove identical contents. Grants and cutover are manual.

## Prepare the demo

The demo uses 100,000 October 2019 events sampled from Michael Kechinov's eCommerce
behavior dataset on Kaggle. Data files are not included. For a new demo only:

1. Run /examples/schema.sql.
2. Prepare a gzip CSV with a header, unique BIGINT event_id values, and UTC timestamps.
   Use the ten-column order in /examples/load.sql; the original has nine columns.
3. Upload it under redshift-migration/source/ in your private S3 bucket. Set the bucket
   name in /examples/load.sql and run it once against empty source and dimension tables.
   Leave the target empty, then follow the run steps above.

## Verification

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

On 4 November 2026, the Redshift demo finished all five chunks with matching counts
and 100,000 rows in each table. Live checks verified rollback, stop/resume without
recopying, and that rerunning YAML setup preserved progress. This was not a throughput benchmark.
