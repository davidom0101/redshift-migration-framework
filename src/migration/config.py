"""Shared YAML settings for setup and migration. Credentials use the AWS chain."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import yaml
from botocore.config import Config


@dataclass
class MigrationConfig:
    migration_id: str
    region: str
    connection: dict[str, str]
    profile: str | None
    wait_timeout_seconds: int
    settings: list[str]
    chunks: list[tuple[str, str]]

    def plan_rows(self) -> list[list[str | int]]:
        return [[i, *self.settings, start, end] for i, (start, end) in enumerate(self.chunks, 1)]

    def create_client(self) -> Any:
        session = boto3.Session(profile_name=self.profile, region_name=self.region)
        return session.client(
            "redshift-data",
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=30),
        )


def text_field(data: dict[str, Any], key: str, limit: int | None = None) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string.")
    if limit is not None and len(value.encode()) > limit:
        raise ValueError(f"{key} exceeds {limit} bytes.")
    return value


def section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping.")
    return value


def timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Chunk dates must be quoted ISO date/time strings in UTC.")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed.isoformat(sep=" ")


def load_config(path: Path) -> MigrationConfig:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("Invalid YAML configuration.") from error
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a mapping.")
    migration_id = text_field(data, "migration_id", 100)
    conn = section(data, "connection")
    workgroup = conn.get("workgroup")
    cluster = conn.get("cluster_identifier")
    if (workgroup is not None) == (cluster is not None):
        raise ValueError("Specify exactly one connection.workgroup or cluster_identifier.")
    selector = "workgroup" if workgroup is not None else "cluster_identifier"
    connection = {
        "WorkgroupName" if workgroup is not None else "ClusterIdentifier": text_field(
            conn, selector
        ),
        "Database": text_field(conn, "database"),
        "SecretArn": text_field(conn, "secret_arn"),
    }
    profile = text_field(conn, "profile") if "profile" in conn else None
    timeout = data.get("wait_timeout_seconds", 3600)
    if type(timeout) is not int or timeout < 1:
        raise ValueError("wait_timeout_seconds must be a positive integer.")
    source, target = section(data, "source"), section(data, "target")
    settings = [
        text_field(source, "schema", 127),
        text_field(source, "table", 127),
        text_field(target, "schema", 127),
        text_field(target, "table", 127),
        text_field(source, "timestamp_column", 127),
    ]
    if settings[:2] == settings[2:4]:
        raise ValueError("Source and target must be different tables.")
    raw_chunks = data.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise ValueError("chunks must be a nonempty list of start/end mappings.")
    chunks = []
    previous_end = None
    for chunk in raw_chunks:
        if not isinstance(chunk, dict):
            raise ValueError("Each chunk must contain start and end.")
        start, end = timestamp(chunk.get("start")), timestamp(chunk.get("end"))
        if start >= end or (previous_end is not None and start != previous_end):
            raise ValueError("Chunks must be ordered and contiguous, with start before end.")
        chunks.append((start, end))
        previous_end = end
    return MigrationConfig(
        migration_id, text_field(conn, "region"), connection, profile, timeout, settings, chunks
    )


def check_stored_plan(config: MigrationConfig, rows: list[list[dict[str, Any]]]) -> None:
    """Compare metadata only; never rewrite status, counts or completion timestamps."""
    actual = []
    for row in rows:
        actual.append(
            [
                int(row[0]["longValue"]),
                *[cell["stringValue"] for cell in row[1:6]],
                timestamp(row[6]["stringValue"]),
                timestamp(row[7]["stringValue"]),
            ]
        )
    if actual != config.plan_rows():
        raise RuntimeError(
            "Stored migration plan differs from YAML. Keep its original settings/ranges."
        )
