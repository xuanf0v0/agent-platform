from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import monotonic
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from amazon_copy.orchestrator.checkpoints import (
    CheckpointBindingError,
    CheckpointClosedError,
    CheckpointConfigurationError,
    CheckpointCorruptionError,
    CheckpointExpiredError,
    CheckpointPolicy,
    CheckpointSerializationError,
    CheckpointStorageError,
    CheckpointStore,
    CheckpointVersionError,
    CheckpointVersions,
    JsonObject,
    MemoryCheckpointStore,
    RequestHash,
    RunHandle,
    RunId,
    SQLiteCheckpointStore,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from pathlib import Path


def test_restart_resume_isolated_and_forbidden_fields_never_reach_sqlite(
    tmp_path: Path,
) -> None:
    # Given: two independent sessions for the same normalized request.
    database = tmp_path / "checkpoints.sqlite3"
    request_hash = sha256(b"same request").hexdigest()
    policy = CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    pending = SQLiteCheckpointStore(database, policy)
    first = pending.start_run(request_hash)
    second = pending.start_run(request_hash)
    with SQLiteCheckpointStore(database, policy) as store:
        # When: each session persists its own normalized state.
        _ = store.save(first, {"stage": "research", "claim_ids": ["claim-1"]})
        _ = store.save(second, {"stage": "critique", "claim_ids": ["claim-2"]})
        with pytest.raises(CheckpointSerializationError):
            _ = store.save(first, {"note": "Authorization: Bearer SECRET_SENTINEL"})

    # Then: restart resumes only the exact handle and no secret reached the file.
    with SQLiteCheckpointStore(database, policy) as reopened:
        first_record = reopened.resume(first)
        second_record = reopened.resume(second)
        assert first_record is not None
        assert first_record.payload["stage"] == "research"
        assert second_record is not None
        assert second_record.payload["stage"] == "critique"
        crossed = RunHandle(
            run_id=first.run_id,
            thread_id=second.thread_id,
            request_hash=first.request_hash,
        )
        with pytest.raises(CheckpointBindingError):
            _ = reopened.resume(crossed)

    assert b"SECRET_SENTINEL" not in database.read_bytes()


def test_memory_store_replaces_latest_revision_and_deletes_by_thread() -> None:
    # Given: an in-memory adapter satisfying the public protocol.
    policy = CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    store = MemoryCheckpointStore(policy)
    handle = store.start_run(sha256(b"memory request").hexdigest())

    # When: the same run is checkpointed twice.
    first = store.save(handle, {"stage": "research"})
    second = store.save(handle, {"stage": "critique"})

    # Then: only the latest revision exists and thread deletion is isolated.
    assert isinstance(store, CheckpointStore)
    assert first.revision == 1
    assert second.revision == 2
    assert store.resume(handle) == second
    assert [summary.revision for summary in store.list_runs()] == [2]
    assert store.delete_thread(handle.thread_id) == 1
    assert store.resume(handle) is None


def test_retention_purges_only_expired_run_and_lists_payload_free_metadata(
    tmp_path: Path,
) -> None:
    # Given: two runs saved 23 hours apart under an injected clock.
    current = [datetime(2026, 1, 1, tzinfo=UTC)]
    policy = CheckpointPolicy(clock=lambda: current[0])
    database = tmp_path / "retention.sqlite3"
    with SQLiteCheckpointStore(database, policy) as store:
        expired = store.start_run(sha256(b"expired").hexdigest())
        _ = store.save(expired, {"stage": "research"})
        current[0] += timedelta(hours=23)
        active = store.start_run(sha256(b"active").hexdigest())
        _ = store.save(active, {"stage": "research"})

        # When: time reaches exactly the first run's retention boundary.
        current[0] += timedelta(hours=1)
        with pytest.raises(CheckpointExpiredError):
            _ = store.save(expired, {"stage": "critique"})
        purged = store.purge_expired()
        summaries = store.list_runs()

        # Then: one payload-free active run survives and can be deleted by thread.
        assert purged == 1
        assert len(summaries) == 1
        assert summaries[0].handle == active
        assert "payload" not in summaries[0].model_dump()
        assert store.resume(expired) is None
        assert store.delete_thread(active.thread_id) == 1
        assert store.list_runs() == ()


@pytest.mark.parametrize(
    "versions",
    [
        CheckpointVersions(state_schema_version=2),
        CheckpointVersions(graph_schema_version=2),
        CheckpointVersions(prompt_version="v2"),
        CheckpointVersions(model_version="v2"),
        CheckpointVersions(provider_version="v2"),
    ],
)
def test_request_and_version_mismatch_require_exact_binding_and_fresh_run(
    tmp_path: Path,
    *,
    versions: CheckpointVersions,
) -> None:
    # Given: a persisted v1 checkpoint.
    database = tmp_path / "versions.sqlite3"
    request_hash = sha256(b"bound request").hexdigest()

    def clock() -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)

    v1 = CheckpointPolicy(clock=clock)
    pending = SQLiteCheckpointStore(database, v1)
    handle = pending.start_run(request_hash)
    with SQLiteCheckpointStore(database, v1) as store:
        _ = store.save(handle, {"stage": "research"})

    # When: callers present another request hash or any incompatible v2 store.
    wrong_request = RunHandle(
        run_id=handle.run_id,
        thread_id=handle.thread_id,
        request_hash=RequestHash(sha256(b"other request").hexdigest()),
    )
    with SQLiteCheckpointStore(database, v1) as reopened, pytest.raises(CheckpointBindingError):
        _ = reopened.resume(wrong_request)
    v2 = CheckpointPolicy(versions=versions, clock=clock)
    with (
        SQLiteCheckpointStore(database, v2) as upgraded,
        pytest.raises(CheckpointVersionError) as captured,
    ):
        _ = upgraded.resume(handle)

    # Then: v1 is never mutated and the typed error supplies an unrelated new run.
    replacement = captured.value.new_run
    assert replacement.run_id != handle.run_id
    assert replacement.thread_id != handle.thread_id
    assert replacement.request_hash == handle.request_hash
    with SQLiteCheckpointStore(database, v1) as unchanged:
        original = unchanged.resume(handle)
        assert original is not None
        assert original.revision == 1


@pytest.mark.parametrize("list_all", [False, True])
def test_corrupt_row_identity_is_rejected_instead_of_cross_resumed(
    tmp_path: Path,
    *,
    list_all: bool,
) -> None:
    # Given: a valid row whose embedded run identity is changed behind the store boundary.
    database = tmp_path / "corrupt.sqlite3"
    policy = CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    pending = SQLiteCheckpointStore(database, policy)
    handle = pending.start_run(sha256(b"corruption request").hexdigest())
    with SQLiteCheckpointStore(database, policy) as store:
        record = store.save(handle, {"stage": "research"})
        corrupt = record.model_copy(
            update={
                "handle": record.handle.model_copy(update={"run_id": RunId(uuid4())}),
            }
        )
        with closing(sqlite3.connect(database)) as setup:
            _ = setup.execute(
                "UPDATE studio_checkpoints SET record_json = ? WHERE run_id = ?",
                (corrupt.model_dump_json(), str(handle.run_id)),
            )
            setup.commit()

    # When/Then: reopening cannot treat mismatched storage identity as the requested run.
    with (
        SQLiteCheckpointStore(database, policy) as reopened,
        pytest.raises(CheckpointCorruptionError) as captured,
    ):
        _ = reopened.list_runs() if list_all else reopened.resume(handle)
    assert captured.value.run_id == (None if list_all else handle.run_id)


def test_failed_sqlite_update_rolls_back_previous_checkpoint(tmp_path: Path) -> None:
    # Given: a committed checkpoint and a trigger that aborts its next update.
    database = tmp_path / "atomic.sqlite3"
    policy = CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    with SQLiteCheckpointStore(database, policy) as store:
        handle = store.start_run(sha256(b"atomic request").hexdigest())
        _ = store.save(handle, {"stage": "research"})
        with closing(sqlite3.connect(database)) as setup:
            _ = setup.execute(
                """
                CREATE TRIGGER abort_checkpoint_update
                BEFORE UPDATE ON studio_checkpoints
                BEGIN SELECT RAISE(ABORT, 'cancelled'); END
                """
            )
            setup.commit()

        # When: SQLite aborts midway through the replacement transaction.
        with pytest.raises(CheckpointStorageError):
            _ = store.save(handle, {"stage": "critique"})

        # Then: the prior revision remains complete and readable after rollback.
        resumed = store.resume(handle)
        assert resumed is not None
        assert resumed.revision == 1
        assert resumed.payload["stage"] == "research"


def test_sqlite_busy_wait_is_bounded_and_leaves_no_partial_run(tmp_path: Path) -> None:
    # Given: an external exclusive lock and a 50ms store busy timeout.
    database = tmp_path / "busy.sqlite3"
    policy = CheckpointPolicy(
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        busy_timeout_seconds=0.05,
    )
    with SQLiteCheckpointStore(database, policy) as store:
        handle = store.start_run(sha256(b"busy request").hexdigest())
        with closing(sqlite3.connect(database, timeout=0.05)) as blocker:
            _ = blocker.execute("BEGIN EXCLUSIVE")
            started = monotonic()

            # When: a save competes with the external writer.
            with pytest.raises(CheckpointStorageError):
                _ = store.save(handle, {"stage": "research"})
            elapsed = monotonic() - started
            blocker.rollback()

        # Then: the wait is bounded and no partial lifecycle record exists.
        assert elapsed < 0.5
        assert store.resume(handle) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"headers": {"Authorization": "redacted"}},
        {"raw_mcp_response": {"result": "redacted"}},
        {"competitor_text": "redacted"},
        {"meeting_transcript": ["redacted"]},
        {"note": "Bearer SECRET_SENTINEL"},
        {"score": float("nan")},
    ],
)
def test_serializer_rejects_sensitive_or_non_json_state(payload: JsonObject) -> None:
    # Given: a fresh memory run and a normalized-JSON-shaped but unsafe payload.
    store = MemoryCheckpointStore(CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)))
    handle = store.start_run(sha256(b"unsafe payload").hexdigest())

    # When: persistence validates the complete payload before mutation.
    with pytest.raises(CheckpointSerializationError):
        _ = store.save(handle, payload)

    # Then: rejection is atomic and the unsafe run remains absent.
    assert store.resume(handle) is None


def test_hash_only_redacted_metadata_is_serializable() -> None:
    # Given: content hashes without the corresponding raw provider data.
    store = MemoryCheckpointStore(CheckpointPolicy(clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)))
    handle = store.start_run(sha256(b"hash metadata").hexdigest())
    payload: JsonObject = {
        "raw_mcp_payload_hash": sha256(b"discarded provider body").hexdigest(),
        "transcript_digest": sha256(b"discarded transcript").hexdigest(),
    }

    # When: the redacted metadata is checkpointed.
    record = store.save(handle, payload)

    # Then: only hashes are present in the stored state.
    assert record.payload == payload


def test_malformed_handles_and_policies_fail_at_the_boundary(tmp_path: Path) -> None:
    # Given: malformed UUID/hash input and retention outside 1-720 hours.
    malformed = {
        "run_id": "not-a-uuid",
        "thread_id": "also-not-a-uuid",
        "request_hash": "short",
    }

    # When/Then: boundary parsing rejects malformed identity and policy values.
    with pytest.raises(ValidationError):
        _ = RunHandle.model_validate(malformed)
    with pytest.raises(CheckpointConfigurationError):
        _ = CheckpointPolicy(retention=timedelta(minutes=59))
    with pytest.raises(CheckpointConfigurationError):
        _ = CheckpointPolicy(retention=timedelta(hours=721))
    closed = SQLiteCheckpointStore(tmp_path / "closed.sqlite3")
    with pytest.raises(CheckpointClosedError):
        _ = closed.list_runs()
