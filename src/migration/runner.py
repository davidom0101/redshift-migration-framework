"""Copy or recheck chunk 1 of the static October example through the Data API.

Run with ``uv run python -m migration.runner``. One operator must keep the source
unchanged, prevent other target writers and resolve any earlier submission first.
"""

import os
import sys
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

MIGRATION_ID = "ecommerce-events-october-demo"
CHUNK_ID = 1


def sql_identifier(value: str) -> str:
    """Quote a database identifier, including any embedded double quotes."""
    return '"' + value.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    """Quote a string value; BatchExecuteStatement SQL is built here explicitly."""
    return "'" + value.replace("'", "''") + "'"


def wait_for_statement(client: Any, statement_id: str) -> dict[str, Any]:
    """Wait up to five minutes without cancelling or resubmitting the statement."""
    print(f"Statement: {statement_id}", flush=True)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        result: dict[str, Any] = client.describe_statement(Id=statement_id)
        status = result["Status"]
        if status == "FINISHED":
            return result
        if status in {"FAILED", "ABORTED"}:
            raise RuntimeError(f"Statement {statement_id}: {status}. {result.get('Error', '')}")
        if status not in {"SUBMITTED", "PICKED", "STARTED"}:
            raise RuntimeError(
                f"Unknown status {status} for {statement_id}; inspect before rerunning."
            )
        time.sleep(2)
    raise RuntimeError(
        f"Stopped waiting for {statement_id}; it may still be running. Do not retry."
    )


def execute_sql(client: Any, connection: dict[str, str], sql: str) -> dict[str, Any]:
    """Submit one statement and return its final description, not its result rows."""
    response = client.execute_statement(**connection, Sql=sql)
    return wait_for_statement(client, response["Id"])


def query(client: Any, connection: dict[str, str], sql: str) -> list[list[dict[str, Any]]]:
    """Read a small result using the Data API's stringValue/longValue cell format."""
    statement = execute_sql(client, connection, sql)
    result = client.get_statement_result(Id=statement["Id"])
    if result.get("NextToken"):
        raise RuntimeError("Unexpected large result; no copy was requested by this query.")
    rows: list[list[dict[str, Any]]] = result["Records"]
    return rows


def read_chunk(
    client: Any,
    connection: dict[str, str],
    migration_id: str,
    chunk_id: int,
) -> dict[str, str]:
    """Read and validate one chunk, returning named settings ready for SQL."""
    chunk_filter = f"migration_id = {sql_literal(migration_id)} AND chunk_id = {chunk_id}"
    rows = query(
        client,
        connection,
        f"""
        SELECT source_schema, source_table, target_schema, target_table,
               timestamp_column, chunk_start, chunk_end, status
        FROM ops.migration_chunks
        WHERE {chunk_filter}
        LIMIT 2
        """,
    )
    if len(rows) != 1:
        raise RuntimeError("Expected exactly one control row; check missing or duplicate chunks.")

    row = rows[0]
    source_schema = row[0]["stringValue"]
    source_table = row[1]["stringValue"]
    target_schema = row[2]["stringValue"]
    target_table = row[3]["stringValue"]
    timestamp_column = row[4]["stringValue"]
    chunk_start = row[5]["stringValue"]
    chunk_end = row[6]["stringValue"]
    status = row[7]["stringValue"]

    if status not in {"PENDING", "DONE"}:
        raise RuntimeError(f"Unsupported chunk status: {status}")
    if datetime.fromisoformat(chunk_start) >= datetime.fromisoformat(chunk_end):
        raise RuntimeError("Chunk start must be before chunk end.")
    if (source_schema, source_table) == (target_schema, target_table):
        raise RuntimeError("Source and target must be different tables.")

    source = f"{sql_identifier(source_schema)}.{sql_identifier(source_table)}"
    target = f"{sql_identifier(target_schema)}.{sql_identifier(target_table)}"
    timestamp = sql_identifier(timestamp_column)
    bounds = (
        f"{timestamp} >= TIMESTAMP {sql_literal(chunk_start)} "
        f"AND {timestamp} < TIMESTAMP {sql_literal(chunk_end)}"
    )

    # Physical keys may differ, but the logical column definitions must match.
    source_columns = query(
        client,
        connection,
        f"""
        SELECT column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, datetime_precision, is_nullable
        FROM information_schema.columns
        WHERE table_schema = {sql_literal(source_schema)}
          AND table_name = {sql_literal(source_table)}
        ORDER BY ordinal_position
        """,
    )
    target_columns = query(
        client,
        connection,
        f"""
        SELECT column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, datetime_precision, is_nullable
        FROM information_schema.columns
        WHERE table_schema = {sql_literal(target_schema)}
          AND table_name = {sql_literal(target_table)}
        ORDER BY ordinal_position
        """,
    )
    if not source_columns or source_columns != target_columns:
        raise RuntimeError("Source and target logical columns must match.")
    column_names = [column[0]["stringValue"] for column in source_columns]
    if timestamp_column not in column_names:
        raise RuntimeError("Chunk timestamp column was not found in the tables.")
    columns = ", ".join(sql_identifier(name) for name in column_names)

    return {
        "source": source,
        "target": target,
        "columns": columns,
        "bounds": bounds,
        "chunk_filter": chunk_filter,
        "statement_name": f"migration-{migration_id}-chunk-{chunk_id}",
        "status": status,
    }


def copy_chunk(client: Any, connection: dict[str, str], chunk: dict[str, str]) -> None:
    """Copy an empty target range and commit its DONE checkpoint in one batch."""
    target_count_sql = f"""
        SELECT COUNT(*) FROM {chunk["target"]}
        WHERE {chunk["bounds"]}
    """
    target_rows = query(client, connection, target_count_sql)
    if target_rows[0][0]["longValue"] != 0:
        raise RuntimeError("Pending chunk's target range is not empty; inspect before copying.")

    copy_sql = f"""
        INSERT INTO {chunk["target"]} ({chunk["columns"]})
        SELECT {chunk["columns"]} FROM {chunk["source"]}
        WHERE {chunk["bounds"]}
    """
    checkpoint_sql = f"""
        UPDATE ops.migration_chunks
        SET status = 'DONE', completed_at = GETDATE()
        WHERE {chunk["chunk_filter"]} AND status = 'PENDING'
    """

    # Print the token before submission so a lost response can be investigated.
    token = str(uuid4())
    print(f"Copy request token: {token}", flush=True)
    try:
        response = client.batch_execute_statement(
            **connection,
            ClientToken=token,
            StatementName=chunk["statement_name"],
            ExecutionMode="TRANSACTION",
            Sqls=[copy_sql, checkpoint_sql],
        )
    except (BotoCoreError, ClientError):
        print("Copy submission failed or its outcome is unknown. Inspect before rerunning.")
        raise
    batch = wait_for_statement(client, response["Id"])
    if batch["SubStatements"][1]["ResultRows"] != 1:
        raise RuntimeError(
            "Copy committed but checkpoint did not affect one row; inspect manually."
        )

    checkpoint_status_sql = f"""
        SELECT status FROM ops.migration_chunks
        WHERE {chunk["chunk_filter"]}
    """
    checkpoint = query(client, connection, checkpoint_status_sql)
    if len(checkpoint) != 1 or checkpoint[0][0]["stringValue"] != "DONE":
        raise RuntimeError("Could not confirm the committed DONE checkpoint; do not recopy.")


def check_counts(client: Any, connection: dict[str, str], chunk: dict[str, str]) -> tuple[int, int]:
    """Save source/target counts and stop on mismatch, leaving the copy committed."""
    # A count failure must not undo DONE: the data copy has already committed.
    count_sql = f"""
        SELECT
            (SELECT COUNT(*) FROM {chunk["source"]} WHERE {chunk["bounds"]}),
            (SELECT COUNT(*) FROM {chunk["target"]} WHERE {chunk["bounds"]})
    """
    counts = query(client, connection, count_sql)
    source_count = int(counts[0][0]["longValue"])
    target_count = int(counts[0][1]["longValue"])
    save_counts_sql = f"""
        UPDATE ops.migration_chunks
        SET source_count = {source_count}, target_count = {target_count}
        WHERE {chunk["chunk_filter"]} AND status = 'DONE'
    """
    saved = execute_sql(client, connection, save_counts_sql)
    if saved["ResultRows"] != 1:
        raise RuntimeError("Counts were not saved to exactly one DONE chunk; inspect manually.")
    print(f"Counts: source={source_count}, target={target_count}")
    if source_count != target_count:
        raise RuntimeError("Count mismatch. The copy remains DONE; do not reset or recopy it.")
    return source_count, target_count


def run_chunk(
    client: Any,
    connection: dict[str, str],
    migration_id: str,
    chunk_id: int,
) -> tuple[int, int]:
    """Copy one pending chunk or recheck a completed chunk without copying again.

    Requires a static source, no other target writers and no unresolved previous
    batch. A failure stops execution; an operator must establish its outcome.
    """
    chunk = read_chunk(client, connection, migration_id, chunk_id)
    print(f"Chunk {chunk_id}: {chunk['status']}")

    if chunk["status"] == "PENDING":
        copy_chunk(client, connection, chunk)
    else:
        print("Copy already committed; checking counts without another INSERT.")

    return check_counts(client, connection, chunk)


def main() -> None:
    """Run the fixed example with external connection settings and AWS credentials."""
    connection = {
        "WorkgroupName": os.environ["REDSHIFT_WORKGROUP"],
        "Database": os.environ["REDSHIFT_DATABASE"],
        "SecretArn": os.environ["REDSHIFT_SECRET_ARN"],
    }
    confirmation = input(
        "Confirm static source, no other writers/runner and no unresolved copy. Type yes: "
    )
    if confirmation != "yes":
        raise SystemExit("No SQL submitted.")
    client = boto3.client(
        "redshift-data",
        region_name=os.environ["AWS_DEFAULT_REGION"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=30),
    )
    run_chunk(client, connection, MIGRATION_ID, CHUNK_ID)


if __name__ == "__main__":
    try:
        main()
    except (BotoCoreError, ClientError, RuntimeError, KeyboardInterrupt) as error:
        print(
            f"Stopped: {error}\nInspect any submitted statements before rerunning.", file=sys.stderr
        )
        raise SystemExit(1) from error
