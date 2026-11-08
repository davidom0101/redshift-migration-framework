"""Create missing control objects and seed one configured migration."""

import argparse
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError

from migration.config import MigrationConfig, check_stored_plan, load_config
from migration.runner import execute_sql, query, sql_identifier, sql_literal, wait_for_statement


def setup_migration(client: Any, config: MigrationConfig) -> None:
    connection = config.connection
    timeout = config.wait_timeout_seconds
    ddl = (Path(__file__).resolve().parents[2] / "sql" / "control_tables.sql").read_text()
    schema_sql, table_sql = ddl.split(";", 1)
    execute_sql(client, connection, schema_sql, timeout)
    execute_sql(
        client,
        connection,
        table_sql.replace(
            "CREATE TABLE ops.migration_chunks", "CREATE TABLE IF NOT EXISTS ops.migration_chunks"
        ),
        timeout,
    )
    columns = query(
        client,
        connection,
        """
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'ops' AND table_name = 'migration_chunks'
        ORDER BY ordinal_position
    """,
        timeout,
    )
    expected = [
        ("migration_id", "character varying", 100, "NO"),
        ("chunk_id", "integer", None, "NO"),
        ("source_schema", "character varying", 127, "NO"),
        ("source_table", "character varying", 127, "NO"),
        ("target_schema", "character varying", 127, "NO"),
        ("target_table", "character varying", 127, "NO"),
        ("timestamp_column", "character varying", 127, "NO"),
        ("chunk_start", "timestamp without time zone", None, "NO"),
        ("chunk_end", "timestamp without time zone", None, "NO"),
        ("status", "character varying", 16, "NO"),
        ("source_count", "bigint", None, "YES"),
        ("target_count", "bigint", None, "YES"),
        ("completed_at", "timestamp without time zone", None, "YES"),
    ]
    actual = [
        (r[0]["stringValue"], r[1]["stringValue"], r[2].get("longValue"), r[3]["stringValue"])
        for r in columns
    ]
    if actual != expected:
        raise RuntimeError(
            "Existing ops.migration_chunks schema is incompatible; review it manually."
        )

    definitions = []
    for schema, table in (config.settings[:2], config.settings[2:4]):
        definitions.append(
            query(
                client,
                connection,
                f"""
            SELECT column_name, data_type, character_maximum_length,
                   numeric_precision, numeric_scale, datetime_precision, is_nullable
            FROM information_schema.columns
            WHERE table_schema = {sql_literal(schema)} AND table_name = {sql_literal(table)}
            ORDER BY ordinal_position
        """,
                timeout,
            )
        )
    if not definitions[0] or definitions[0] != definitions[1]:
        raise RuntimeError("Create source and target with matching logical columns before setup.")
    if config.settings[4] not in [r[0]["stringValue"] for r in definitions[0]]:
        raise RuntimeError("Timestamp column not found in source/target.")

    stored = query(
        client,
        connection,
        f"""
        SELECT chunk_id, source_schema, source_table, target_schema, target_table,
               timestamp_column, chunk_start, chunk_end
        FROM ops.migration_chunks
        WHERE migration_id = {sql_literal(config.migration_id)} ORDER BY chunk_id
    """,
        timeout,
    )
    if stored:
        check_stored_plan(config, stored)
        print("Matching migration already exists. Progress unchanged; run the migration to resume.")
        return

    source = ".".join(sql_identifier(v) for v in config.settings[:2])
    target = ".".join(sql_identifier(v) for v in config.settings[2:4])
    timestamp = sql_identifier(config.settings[4])
    start, end = config.chunks[0][0], config.chunks[-1][1]
    counts = query(
        client,
        connection,
        f"""
        SELECT (SELECT COUNT(*) FROM {target}),
               (SELECT COUNT(*) FROM {source}
                WHERE {timestamp} IS NULL OR {timestamp} < TIMESTAMP {sql_literal(start)}
                      OR {timestamp} >= TIMESTAMP {sql_literal(end)})
    """,
        timeout,
    )
    if any(cell["longValue"] != 0 for cell in counts[0]):
        raise RuntimeError(
            "New migration needs an empty target and no NULL/out-of-window source dates."
        )
    values = []
    for row in config.plan_rows():
        chunk_id = row[0]
        literals = [sql_literal(str(value)) for value in row[1:]]
        values.append(
            f"({sql_literal(config.migration_id)}, {chunk_id}, {', '.join(literals)}, 'PENDING')"
        )
    seed_sql = """
        INSERT INTO ops.migration_chunks (
            migration_id, chunk_id, source_schema, source_table, target_schema,
            target_table, timestamp_column, chunk_start, chunk_end, status
        ) VALUES
    """ + ",\n".join(values)
    token = str(uuid4())
    print(f"Setup request token: {token}", flush=True)
    response = client.batch_execute_statement(
        **connection,
        ClientToken=token,
        StatementName=f"migration-{config.migration_id}-setup",
        ExecutionMode="TRANSACTION",
        Sqls=[seed_sql],
    )
    result = wait_for_statement(client, response["Id"], timeout)
    if result["SubStatements"][0]["ResultRows"] != len(config.chunks):
        raise RuntimeError("Unexpected seed count; inspect setup before rerunning.")
    print(f"Seeded {len(config.chunks)} PENDING chunks. Target data was not changed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare control rows; target creation stays manual."
    )
    parser.add_argument("--config", type=Path, required=True, help="Migration YAML file.")
    args = parser.parse_args()
    config = load_config(args.config)
    confirmation = input("Confirm one operator and no unresolved setup/copy. Type yes: ")
    if confirmation != "yes":
        raise SystemExit("No SQL submitted.")
    setup_migration(config.create_client(), config)


if __name__ == "__main__":
    try:
        main()
    except (
        BotoCoreError,
        ClientError,
        RuntimeError,
        ValueError,
        OSError,
        KeyboardInterrupt,
    ) as error:
        print(f"Stopped: {error}\nInspect submitted statements before rerunning.", file=sys.stderr)
        raise SystemExit(1) from error
