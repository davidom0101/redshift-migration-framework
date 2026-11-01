from unittest.mock import Mock

import pytest
from botocore.exceptions import EndpointConnectionError

from migration import runner

CONNECTION = {"WorkgroupName": "test-workgroup", "Database": "test-db", "SecretArn": "test-secret"}


@pytest.fixture
def client():
    client = Mock()
    client.batch_execute_statement.return_value = {"Id": "copy-statement"}
    client.execute_statement.return_value = {"Id": "count-update"}
    client.describe_statement.return_value = {
        "Status": "FINISHED",
        "ResultRows": 1,
        "SubStatements": [{"ResultRows": 3}, {"ResultRows": 1}],
    }
    return client


@pytest.fixture
def loaded_chunk(monkeypatch):
    chunk = {
        "source": '"demo"."fact_events_source"',
        "target": '"demo"."fact_events_rebuilt"',
        "columns": '"event_id", "event_time"',
        "bounds": "\"event_time\" >= TIMESTAMP '2019-10-01 00:00:00' "
        "AND \"event_time\" < TIMESTAMP '2019-10-08 00:00:00'",
        "chunk_filter": "migration_id = 'example' AND chunk_id = 1",
        "statement_name": "migration-example-chunk-1",
        "status": "PENDING",
    }
    monkeypatch.setattr(runner, "read_chunk", Mock(return_value=chunk))
    return chunk


@pytest.mark.parametrize("row_count", [0, 3])
def test_pending_chunk_copies_checkpoints_and_saves_counts(
    monkeypatch, client, loaded_chunk, row_count
):
    empty_target = [[{"longValue": 0}]]
    done_checkpoint = [[{"stringValue": "DONE"}]]
    matching_counts = [[{"longValue": row_count}, {"longValue": row_count}]]
    queries = Mock(side_effect=[empty_target, done_checkpoint, matching_counts])
    monkeypatch.setattr(runner, "query", queries)

    assert runner.run_chunk(client, CONNECTION, "example", 1) == (row_count, row_count)

    client.batch_execute_statement.assert_called_once()
    batch = client.batch_execute_statement.call_args.kwargs
    assert batch["ExecutionMode"] == "TRANSACTION"
    copy_sql, checkpoint_sql = batch["Sqls"]
    assert f"INSERT INTO {loaded_chunk['target']} ({loaded_chunk['columns']})" in copy_sql
    assert f"SELECT {loaded_chunk['columns']} FROM {loaded_chunk['source']}" in copy_sql
    assert loaded_chunk["bounds"] in copy_sql
    assert "SET status = 'DONE'" in checkpoint_sql
    assert f"WHERE {loaded_chunk['chunk_filter']} AND status = 'PENDING'" in checkpoint_sql
    count_sql = queries.call_args.args[2]
    assert f"FROM {loaded_chunk['source']} WHERE {loaded_chunk['bounds']}" in count_sql
    assert f"FROM {loaded_chunk['target']} WHERE {loaded_chunk['bounds']}" in count_sql
    saved_sql = client.execute_statement.call_args.kwargs["Sql"]
    assert f"SET source_count = {row_count}, target_count = {row_count}" in saved_sql
    assert "WHERE migration_id = 'example' AND chunk_id = 1 AND status = 'DONE'" in saved_sql


def test_done_chunk_rechecks_counts_without_copying(monkeypatch, client, loaded_chunk):
    loaded_chunk["status"] = "DONE"
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 3}, {"longValue": 3}]]))

    assert runner.run_chunk(client, CONNECTION, "example", 1) == (3, 3)

    client.batch_execute_statement.assert_not_called()
    assert (
        "SET source_count = 3, target_count = 3" in client.execute_statement.call_args.kwargs["Sql"]
    )


def test_count_mismatch_is_saved_without_resetting_done(monkeypatch, client, loaded_chunk):
    loaded_chunk["status"] = "DONE"
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 3}, {"longValue": 2}]]))

    with pytest.raises(RuntimeError, match="Count mismatch"):
        runner.run_chunk(client, CONNECTION, "example", 1)

    client.batch_execute_statement.assert_not_called()
    saved_sql = client.execute_statement.call_args.kwargs["Sql"]
    assert "SET source_count = 3, target_count = 2" in saved_sql
    assert "SET status" not in saved_sql


def test_nonempty_pending_target_is_not_copied(monkeypatch, client, loaded_chunk):
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 2}]]))

    with pytest.raises(RuntimeError, match="target range is not empty"):
        runner.run_chunk(client, CONNECTION, "example", 1)

    client.batch_execute_statement.assert_not_called()
    client.execute_statement.assert_not_called()


@pytest.mark.parametrize("status", ["FAILED", "STARTED"])
def test_failed_or_unresolved_copy_stops_without_retry(monkeypatch, client, loaded_chunk, status):
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 0}]]))
    monkeypatch.setattr(runner.time, "monotonic", Mock(side_effect=[0, 0, 301]))
    monkeypatch.setattr(runner.time, "sleep", Mock())
    client.describe_statement.return_value = {"Status": status}

    with pytest.raises(RuntimeError):
        runner.run_chunk(client, CONNECTION, "example", 1)

    client.batch_execute_statement.assert_called_once()
    client.execute_statement.assert_not_called()
    client.cancel_statement.assert_not_called()


def test_lost_submission_response_is_not_retried(monkeypatch, client, loaded_chunk):
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 0}]]))
    client.batch_execute_statement.side_effect = EndpointConnectionError(
        endpoint_url="https://example.invalid"
    )

    with pytest.raises(EndpointConnectionError):
        runner.run_chunk(client, CONNECTION, "example", 1)

    client.batch_execute_statement.assert_called_once()
    client.execute_statement.assert_not_called()


def test_failed_count_save_stops_without_another_copy(monkeypatch, client, loaded_chunk):
    loaded_chunk["status"] = "DONE"
    monkeypatch.setattr(runner, "query", Mock(return_value=[[{"longValue": 3}, {"longValue": 3}]]))
    client.describe_statement.return_value["ResultRows"] = 0

    with pytest.raises(RuntimeError, match="Counts were not saved"):
        runner.run_chunk(client, CONNECTION, "example", 1)

    client.batch_execute_statement.assert_not_called()
