from pathlib import Path
from unittest.mock import Mock

import pytest

from migration import setup
from migration.config import load_config


@pytest.fixture
def config():
    return load_config(Path("examples/migration.yaml"))


def stored_rows(config):
    return [
        [{"longValue": row[0]}, *[{"stringValue": v} for v in row[1:]]]
        for row in config.plan_rows()
    ]


def mock_reads(monkeypatch, config, stored):
    columns = []
    names = [
        "migration_id",
        "chunk_id",
        "source_schema",
        "source_table",
        "target_schema",
        "target_table",
        "timestamp_column",
        "chunk_start",
        "chunk_end",
        "status",
        "source_count",
        "target_count",
        "completed_at",
    ]
    for name in names:
        length = 100 if name == "migration_id" else 16 if name == "status" else 127
        kind = "character varying"
        if name == "chunk_id":
            kind = "integer"
        elif name in {"source_count", "target_count"}:
            kind = "bigint"
        elif name in {"chunk_start", "chunk_end", "completed_at"}:
            kind = "timestamp without time zone"
        columns.append(
            [
                {"stringValue": name},
                {"stringValue": kind},
                {"longValue": length} if kind == "character varying" else {"isNull": True},
                {"stringValue": "YES" if name in names[-3:] else "NO"},
            ]
        )
    logical_columns = [[{"stringValue": "event_time"}]]
    monkeypatch.setattr(
        setup,
        "query",
        Mock(
            side_effect=[
                columns,
                logical_columns,
                logical_columns,
                stored,
                [[{"longValue": 0}, {"longValue": 0}]],
            ]
        ),
    )
    execute = Mock()
    monkeypatch.setattr(setup, "execute_sql", execute)
    return execute


def test_new_setup_seeds_pending_chunks_without_copying(monkeypatch, config):
    mock_reads(monkeypatch, config, [])
    client = Mock()
    client.batch_execute_statement.return_value = {"Id": "seed"}
    monkeypatch.setattr(
        setup,
        "wait_for_statement",
        Mock(
            return_value={
                "SubStatements": [{"ResultRows": 5}],
            }
        ),
    )
    setup.setup_migration(client, config)
    sql = client.batch_execute_statement.call_args.kwargs["Sqls"][0]
    assert "INSERT INTO ops.migration_chunks" in sql
    assert sql.count("'PENDING'") == 5
    assert "INSERT INTO demo" not in sql


def test_existing_matching_setup_preserves_progress(monkeypatch, config):
    execute = mock_reads(monkeypatch, config, stored_rows(config))
    client = Mock()
    setup.setup_migration(client, config)
    client.batch_execute_statement.assert_not_called()
    assert len(execute.call_args_list) == 2
    assert all("UPDATE" not in call.args[2] for call in execute.call_args_list)


def test_changed_plan_refused_without_reseeding(monkeypatch, config):
    rows = stored_rows(config)
    rows[0][2] = {"stringValue": "different_table"}
    mock_reads(monkeypatch, config, rows)
    client = Mock()
    with pytest.raises(RuntimeError, match="differs from YAML"):
        setup.setup_migration(client, config)
    client.batch_execute_statement.assert_not_called()


def test_invalid_yaml_plan_refused_before_aws(tmp_path):
    text = Path("examples/migration.yaml").read_text()
    path = tmp_path / "bad.yaml"
    path.write_text(text.replace('end: "2019-10-08 00:00:00"', 'end: "2019-10-09 00:00:00"'))
    with pytest.raises(ValueError, match="contiguous"):
        load_config(path)
