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

## Run one chunk

Git Bash, from the project root, using your existing AWS credentials:

```bash
uv sync
export AWS_DEFAULT_REGION="eu-west-1"
export REDSHIFT_WORKGROUP="migration-dev"
export REDSHIFT_DATABASE="migration_lab"
export REDSHIFT_SECRET_ARN='<database credentials secret ARN>'
uv run python -m migration.runner
```

Runs chunk 1 and checks row counts after committing. Reruns recheck DONE chunks
without copying them again.

Keep the source unchanged and run one migration at a time. After a failure, check the previous query’s outcome before rerunning.
