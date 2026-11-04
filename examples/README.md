# E-commerce example

100,000 October 2019 events sampled from Michael Kechinov's
[eCommerce dataset](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store). 
Data files are not included.

## Setup

1. In a new database, run schema.sql and control_tables.sql
2. Prepare a gzip CSV with a header, unique BIGINT event_id values and UTC
   timestamps. Use the ten column order in load.sql, the original
   dataset has nine columns and needs event_id added.
3. Upload it under redshift-migration/source/ in your private S3 bucket, set the
   bucket name in load.sql and run it once against empty source/dimension tables.
   Leave the replacement table empty.
4. Confirm the source is stable and this migration has no existing chunk rows,
   then run chunks.sql once to seed the five October chunks.
   Skip it when resuming; rerunning inserts duplicates.

## Run and resume

Follow the root README for connection variables and commands.
Run `uv run python -m migration.runner --max-chunks 1` to stop after one newly copied
chunk; rerun without the limit to finish. DONE chunks are rechecked without recopying.
Do not rerun setup, load or chunk seeding scripts when resuming.

The offline checks use `uv run pytest -q`. Live acceptance is a manual demo run with
checkpoint/count inspection. A one-time rollback check on disposable fixtures passed
on 4 November 2026; its automated AWS harness was subsequently removed to keep this
project small.

The full demo completed on 4 November 2026: five DONE chunks with matching counts,
100,000 source rows and 100,000 target rows. A clean stop after chunk 2 and restart
verified that completed copies were skipped.
