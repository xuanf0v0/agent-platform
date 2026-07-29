"""Redacted checkpoint persistence boundary for studio runs.

# noqa: SIZE_OK — the approved plan assigns the protocol and both adapters to one module.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from math import isfinite
from pathlib import Path
from threading import RLock
from typing import (
    TYPE_CHECKING,
    Annotated,
    ClassVar,
    Final,
    Literal,
    NewType,
    Protocol,
    Self,
    TypeAlias,
    assert_never,
    runtime_checkable,
)
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from typing_extensions import override  # noqa: UP035 — Python 3.11 compatibility

if TYPE_CHECKING:
    from types import TracebackType

RunId = NewType("RunId", UUID)
ThreadId = NewType("ThreadId", UUID)
RequestHash = NewType("RequestHash", str)
JsonObject: TypeAlias = dict[str, JsonValue]  # noqa: UP040 — Python 3.11 compatibility
Clock: TypeAlias = Callable[[], datetime]  # noqa: UP040 — Python 3.11 compatibility
VersionLabel: TypeAlias = Annotated[  # noqa: UP040 — Python 3.11 compatibility
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$"),
]

_DEFAULT_RETENTION: Final = timedelta(hours=24)
_MAX_RETENTION: Final = timedelta(hours=720)
_MAX_BUSY_TIMEOUT_SECONDS: Final = 30.0
_UUID4_VERSION: Final = 4
_JSON_ADAPTER: Final = TypeAdapter(JsonObject, config=ConfigDict(strict=True))
_FORBIDDEN_KEYS: Final = frozenset(
    {
        "api_key",
        "authorization",
        "auth_header",
        "auth_headers",
        "credential",
        "credentials",
        "password",
        "secret",
        "access_token",
        "refresh_token",
        "raw",
        "raw_body",
        "raw_content",
        "raw_data",
        "raw_payload",
        "raw_response",
        "mcp_payload",
        "mcp_response",
        "competitor_block",
        "competitor_body",
        "competitor_copy",
        "competitor_text",
        "full_competitor",
        "meeting_transcript",
        "raw_transcript",
        "transcript",
    }
)
_SENSITIVE_HEADER_PATTERN: Final = r"authorization\s*[:=]|bearer\s+[A-Za-z0-9._~+/=-]{4,}"
_SENSITIVE_ASSIGNMENT_PATTERN: Final = (
    r"(?:api[_ -]?key|password|secret|access[_ -]?token|refresh[_ -]?token)\s*[:=]"
)
_PEM_PATTERN: Final = r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
_SENSITIVE_VALUE: Final = re.compile(
    f"secret_sentinel|{_SENSITIVE_HEADER_PATTERN}|{_SENSITIVE_ASSIGNMENT_PATTERN}|{_PEM_PATTERN}",
    re.IGNORECASE,
)


class CheckpointError(Exception):
    """Base class for safe checkpoint boundary failures."""


@dataclass(frozen=True, slots=True)
class CheckpointSerializationError(CheckpointError):
    """State was not normalized, redacted JSON."""

    path: str
    reason: str

    @override
    def __str__(self) -> str:
        """Return a redacted rejection description."""
        return f"checkpoint payload rejected at {self.path}: {self.reason}"


@dataclass(frozen=True, slots=True)
class CheckpointBindingError(CheckpointError):
    """A resume handle did not match persisted run ownership."""

    run_id: RunId
    field: Literal["thread_id", "request_hash"]

    @override
    def __str__(self) -> str:
        """Return the mismatched binding field without its value."""
        return f"checkpoint {self.run_id} does not match {self.field}"


@dataclass(frozen=True, slots=True)
class CheckpointClosedError(CheckpointError):
    """A SQLite operation was attempted outside the store context."""

    path: Path

    @override
    def __str__(self) -> str:
        """Return the closed store path."""
        return f"checkpoint store is closed: {self.path}"


@dataclass(frozen=True, slots=True)
class CheckpointStorageError(CheckpointError):
    """SQLite could not complete one bounded storage operation."""

    operation: Literal["open", "read", "save", "list", "delete", "purge"]

    @override
    def __str__(self) -> str:
        """Return the failed operation without SQLite internals."""
        return f"checkpoint storage operation failed: {self.operation}"


@dataclass(frozen=True, slots=True)
class CheckpointCorruptionError(CheckpointError):
    """Persisted bytes did not decode as the application-owned schema."""

    run_id: RunId | None

    @override
    def __str__(self) -> str:
        """Return a payload-free corruption description."""
        return "checkpoint data is incompatible with its storage schema"


@dataclass(frozen=True, slots=True)
class CheckpointConfigurationError(CheckpointError):
    """Checkpoint retention, clock, or lock-wait policy was invalid."""

    field: Literal["retention", "clock", "busy_timeout_seconds"]

    @override
    def __str__(self) -> str:
        """Return the invalid policy field."""
        return f"invalid checkpoint configuration: {self.field}"


class CheckpointVersions(BaseModel):
    """Application versions bound to every persisted state."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    state_schema_version: int = Field(default=1, ge=1)
    graph_schema_version: int = Field(default=1, ge=1)
    prompt_version: VersionLabel = "v1"
    model_version: VersionLabel = "v1"
    provider_version: VersionLabel = "v1"

    @field_validator("prompt_version", "model_version", "provider_version")
    @classmethod
    def _reject_secret_label(cls, value: str) -> str:
        if _SENSITIVE_VALUE.search(value):
            msg = "version labels cannot contain secret-bearing content"
            raise ValueError(msg)
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CheckpointPolicy:
    """Retention, compatibility, clock, and bounded lock-wait policy."""

    versions: CheckpointVersions = field(default_factory=CheckpointVersions)
    retention: timedelta = _DEFAULT_RETENTION
    clock: Clock = _utc_now
    busy_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        """Reject policies outside the configured retention and lock bounds."""
        if not _DEFAULT_RETENTION <= self.retention <= _MAX_RETENTION:
            raise CheckpointConfigurationError(field="retention")
        if not 0 < self.busy_timeout_seconds <= _MAX_BUSY_TIMEOUT_SECONDS:
            raise CheckpointConfigurationError(field="busy_timeout_seconds")

    def now(self) -> datetime:
        """Return an injected, normalized UTC instant."""
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise CheckpointConfigurationError(field="clock")
        return value.astimezone(UTC)


class RunHandle(BaseModel):
    """Unpredictable run/thread identity plus exact request binding."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    run_id: RunId
    thread_id: ThreadId
    request_hash: RequestHash = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("run_id")
    @classmethod
    def _run_id_is_uuid4(cls, value: RunId) -> RunId:
        if value.version != _UUID4_VERSION:
            msg = "run_id must be UUID4"
            raise ValueError(msg)
        return value

    @field_validator("thread_id")
    @classmethod
    def _thread_id_is_uuid4(cls, value: ThreadId) -> ThreadId:
        if value.version != _UUID4_VERSION:
            msg = "thread_id must be UUID4"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _ids_are_distinct(self) -> Self:
        if self.run_id == self.thread_id:
            msg = "run_id and thread_id must differ"
            raise ValueError(msg)
        return self


class CheckpointRecord(BaseModel):
    """One latest, redacted state snapshot."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    handle: RunHandle
    versions: CheckpointVersions
    payload: JsonObject
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def _timestamps_are_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            msg = "checkpoint timestamps must be UTC"
            raise ValueError(msg)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _lifecycle_is_ordered(self) -> Self:
        if not self.created_at <= self.updated_at < self.expires_at:
            msg = "checkpoint lifecycle timestamps are out of order"
            raise ValueError(msg)
        return self


class CheckpointSummary(BaseModel):
    """Payload-free run metadata returned by list operations."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    handle: RunHandle
    versions: CheckpointVersions
    revision: int
    updated_at: datetime
    expires_at: datetime

    @classmethod
    def from_record(cls, record: CheckpointRecord) -> CheckpointSummary:
        """Project a checkpoint without its payload."""
        return cls(
            handle=record.handle,
            versions=record.versions,
            revision=record.revision,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
        )


@dataclass(frozen=True, slots=True)
class CheckpointVersionError(CheckpointError):
    """Persisted state was incompatible and a fresh run is required."""

    run_id: RunId
    stored: CheckpointVersions
    expected: CheckpointVersions
    new_run: RunHandle

    @override
    def __str__(self) -> str:
        """Return the incompatible run without version internals."""
        return f"checkpoint {self.run_id} has incompatible application versions"


@dataclass(frozen=True, slots=True)
class CheckpointExpiredError(CheckpointError):
    """An expired run cannot be mutated and has a fresh replacement."""

    run_id: RunId
    new_run: RunHandle

    @override
    def __str__(self) -> str:
        """Return the expired run identifier."""
        return f"checkpoint {self.run_id} has expired"


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _key_is_forbidden(value: str) -> bool:
    key = _normalized_key(value)
    if key.endswith(("_hash", "_digest")) and any(
        part in key for part in ("raw", "mcp", "competitor", "transcript")
    ):
        return False
    return key in _FORBIDDEN_KEYS or any(
        part in key
        for part in (
            "authorization",
            "credential",
            "password",
            "api_key",
            "access_token",
            "refresh_token",
            "raw_mcp",
            "mcp_payload",
            "mcp_response",
            "full_competitor",
            "raw_transcript",
            "meeting_transcript",
        )
    )


def _reject_mapping(mapping: dict[str, JsonValue], path: str) -> None:
    for key, item in mapping.items():
        item_path = f"{path}.{key}"
        if _key_is_forbidden(key):
            raise CheckpointSerializationError(path=item_path, reason="forbidden field")
        _reject_forbidden(item, item_path)


def _reject_sequence(items: list[JsonValue], path: str) -> None:
    for index, item in enumerate(items):
        _reject_forbidden(item, f"{path}[{index}]")


def _reject_forbidden(value: JsonValue, path: str) -> None:
    match value:
        case dict() as mapping:
            _reject_mapping(mapping, path)
        case list() as items:
            _reject_sequence(items, path)
        case str() as text:
            if _SENSITIVE_VALUE.search(text):
                raise CheckpointSerializationError(path=path, reason="secret-bearing value")
        case float() as number:
            if not isfinite(number):
                raise CheckpointSerializationError(path=path, reason="non-finite number")
        case None | bool() | int():
            return
        case _:
            assert_never(value)


def _normalize_payload(payload: JsonObject) -> JsonObject:
    try:
        normalized = _JSON_ADAPTER.validate_python(payload, strict=True)
    except ValidationError as exc:
        raise CheckpointSerializationError(path="$", reason="payload must be strict JSON") from exc
    _reject_forbidden(normalized, "$")
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _JSON_ADAPTER.validate_json(encoded, strict=True)


@runtime_checkable
class CheckpointStore(Protocol):
    """Application-owned persistence contract exposed to graph orchestration."""

    def start_run(self, request_hash: str) -> RunHandle:
        """Create an unpredictable, request-bound run handle."""
        ...

    def save(self, handle: RunHandle, payload: JsonObject) -> CheckpointRecord:
        """Atomically insert or replace the latest redacted state."""
        ...

    def resume(self, handle: RunHandle) -> CheckpointRecord | None:
        """Load state only for the exact request and run/thread pair."""
        ...

    def list_runs(self, thread_id: ThreadId | None = None) -> tuple[CheckpointSummary, ...]:
        """List active payload-free run metadata."""
        ...

    def delete_thread(self, thread_id: ThreadId) -> int:
        """Delete the run owned by one thread and return the row count."""
        ...

    def purge_expired(self) -> int:
        """Delete expired runs using the injected UTC clock."""
        ...


class _StoreRules:
    def __init__(self, policy: CheckpointPolicy | None) -> None:
        self._policy: CheckpointPolicy = policy or CheckpointPolicy()

    @property
    def policy(self) -> CheckpointPolicy:
        return self._policy

    def start_run(self, request_hash: str) -> RunHandle:
        run_id = RunId(uuid4())
        thread_id = ThreadId(uuid4())
        while run_id == thread_id:
            thread_id = ThreadId(uuid4())
        return RunHandle(
            run_id=run_id,
            thread_id=thread_id,
            request_hash=RequestHash(request_hash),
        )

    def _check_binding(self, record: CheckpointRecord, handle: RunHandle) -> None:
        if record.handle.thread_id != handle.thread_id:
            raise CheckpointBindingError(run_id=handle.run_id, field="thread_id")
        if not compare_digest(str(record.handle.request_hash), str(handle.request_hash)):
            raise CheckpointBindingError(run_id=handle.run_id, field="request_hash")
        if record.versions != self.policy.versions:
            raise CheckpointVersionError(
                run_id=handle.run_id,
                stored=record.versions,
                expected=self.policy.versions,
                new_run=self.start_run(str(handle.request_hash)),
            )

    def _next_record(
        self,
        handle: RunHandle,
        payload: JsonObject,
        previous: CheckpointRecord | None,
    ) -> CheckpointRecord:
        now = self.policy.now()
        if previous is not None:
            self._check_binding(previous, handle)
            if previous.expires_at <= now:
                raise CheckpointExpiredError(
                    run_id=handle.run_id,
                    new_run=self.start_run(str(handle.request_hash)),
                )
        return CheckpointRecord(
            handle=handle,
            versions=self.policy.versions,
            payload=payload,
            revision=1 if previous is None else previous.revision + 1,
            created_at=now if previous is None else previous.created_at,
            updated_at=now,
            expires_at=now + self.policy.retention,
        )


class MemoryCheckpointStore(_StoreRules):
    """Thread-safe in-memory implementation of the checkpoint contract."""

    def __init__(self, policy: CheckpointPolicy | None = None) -> None:
        """Initialize isolated mutable storage under a reentrant lock."""
        super().__init__(policy)
        self._records: dict[RunId, CheckpointRecord] = {}
        self._lock: RLock = RLock()

    def save(self, handle: RunHandle, payload: JsonObject) -> CheckpointRecord:
        """Atomically insert or update one in-memory run."""
        normalized = _normalize_payload(payload)
        with self._lock:
            previous = self._records.get(handle.run_id)
            if previous is None and any(
                record.handle.thread_id == handle.thread_id for record in self._records.values()
            ):
                raise CheckpointBindingError(run_id=handle.run_id, field="thread_id")
            record = self._next_record(handle, normalized, previous)
            self._records[handle.run_id] = record.model_copy(deep=True)
            return record.model_copy(deep=True)

    def resume(self, handle: RunHandle) -> CheckpointRecord | None:
        """Return a detached copy for an active exact-bound run."""
        with self._lock:
            record = self._records.get(handle.run_id)
            if record is None:
                return None
            self._check_binding(record, handle)
            if record.expires_at <= self.policy.now():
                return None
            return record.model_copy(deep=True)

    def list_runs(self, thread_id: ThreadId | None = None) -> tuple[CheckpointSummary, ...]:
        """List active runs without state payloads."""
        now = self.policy.now()
        with self._lock:
            records = (
                record
                for record in self._records.values()
                if record.expires_at > now
                and (thread_id is None or record.handle.thread_id == thread_id)
            )
            ordered = sorted(
                records,
                key=lambda record: (record.updated_at, str(record.handle.run_id)),
                reverse=True,
            )
            return tuple(CheckpointSummary.from_record(record) for record in ordered)

    def delete_thread(self, thread_id: ThreadId) -> int:
        """Delete the run associated with one thread."""
        with self._lock:
            run_ids = [
                run_id
                for run_id, record in self._records.items()
                if record.handle.thread_id == thread_id
            ]
            for run_id in run_ids:
                del self._records[run_id]
            return len(run_ids)

    def purge_expired(self) -> int:
        """Delete every run whose retention deadline passed."""
        now = self.policy.now()
        with self._lock:
            expired = [
                run_id for run_id, record in self._records.items() if record.expires_at <= now
            ]
            for run_id in expired:
                del self._records[run_id]
            return len(expired)


_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS studio_checkpoints (
    run_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS studio_checkpoints_expiry ON studio_checkpoints(expires_at);
"""


class _TextCursor(Protocol):
    def fetchone(self) -> tuple[str, str] | None: ...

    def fetchall(self) -> list[tuple[str, str]]: ...


def _fetch_one(cursor: _TextCursor) -> tuple[str, str] | None:
    return cursor.fetchone()


def _fetch_all(cursor: _TextCursor) -> list[tuple[str, str]]:
    return cursor.fetchall()


class _Transaction:
    def __init__(
        self,
        connection: sqlite3.Connection,
        operation: Literal["save", "delete", "purge"],
    ) -> None:
        self._connection: sqlite3.Connection = connection
        self._operation: Literal["save", "delete", "purge"] = operation

    def __enter__(self) -> sqlite3.Connection:
        try:
            _ = self._connection.__enter__()
            _ = self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.DatabaseError as exc:
            raise CheckpointStorageError(operation=self._operation) from exc
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            _ = self._connection.__exit__(exc_type, exc, traceback)
        except sqlite3.DatabaseError as error:
            raise CheckpointStorageError(operation=self._operation) from error
        if isinstance(exc, sqlite3.DatabaseError):
            raise CheckpointStorageError(operation=self._operation) from exc
        return False


class SQLiteCheckpointStore(_StoreRules):
    """Context-managed, transactionally atomic SQLite checkpoint store."""

    def __init__(self, path: str | Path, policy: CheckpointPolicy | None = None) -> None:
        """Configure a store without opening a database handle."""
        super().__init__(policy)
        self.path: Path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock: RLock = RLock()

    def __enter__(self) -> Self:
        """Open the database and initialize its private schema."""
        with self._lock:
            if self._connection is not None:
                return self
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection: sqlite3.Connection | None = None
            try:
                connection = sqlite3.connect(
                    self.path,
                    timeout=self.policy.busy_timeout_seconds,
                    check_same_thread=False,
                )
                with connection:
                    _ = connection.executescript(_SCHEMA)
            except sqlite3.DatabaseError as exc:
                if connection is not None:
                    connection.close()
                raise CheckpointStorageError(operation="open") from exc
            self._connection = connection
            return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Close the exact database connection owned by this context."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
        return False

    def _open_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise CheckpointClosedError(path=self.path)
        return self._connection

    def _transaction(
        self,
        operation: Literal["save", "delete", "purge"],
    ) -> _Transaction:
        return _Transaction(self._open_connection(), operation)

    @staticmethod
    def _decode(row: tuple[str, str] | None, run_id: RunId | None) -> CheckpointRecord | None:
        if row is None:
            return None
        try:
            record = CheckpointRecord.model_validate_json(row[1])
            _ = _normalize_payload(record.payload)
        except (ValidationError, CheckpointSerializationError) as exc:
            raise CheckpointCorruptionError(run_id=run_id) from exc
        if str(record.handle.run_id) != row[0]:
            raise CheckpointCorruptionError(run_id=run_id)
        return record

    def _read(self, connection: sqlite3.Connection, run_id: RunId) -> CheckpointRecord | None:
        return self._decode(
            _fetch_one(
                connection.execute(
                    "SELECT run_id, record_json FROM studio_checkpoints WHERE run_id = ?",
                    (str(run_id),),
                )
            ),
            run_id,
        )

    def save(self, handle: RunHandle, payload: JsonObject) -> CheckpointRecord:
        """Persist one latest state in an immediate transaction."""
        normalized = _normalize_payload(payload)
        with self._lock, self._transaction("save") as connection:
            previous = self._read(connection, handle.run_id)
            if previous is None:
                collision = _fetch_one(
                    connection.execute(
                        "SELECT run_id, record_json FROM studio_checkpoints WHERE thread_id = ?",
                        (str(handle.thread_id),),
                    )
                )
                if collision is not None:
                    raise CheckpointBindingError(run_id=handle.run_id, field="thread_id")
            record = self._next_record(handle, normalized, previous)
            _ = connection.execute(
                """
                INSERT INTO studio_checkpoints(run_id, thread_id, expires_at, record_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    expires_at = excluded.expires_at,
                    record_json = excluded.record_json
                """,
                (
                    str(handle.run_id),
                    str(handle.thread_id),
                    record.expires_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
            return record

    def resume(self, handle: RunHandle) -> CheckpointRecord | None:
        """Resume only an active checkpoint with exact bindings."""
        with self._lock:
            connection = self._open_connection()
            try:
                record = self._read(connection, handle.run_id)
            except sqlite3.DatabaseError as exc:
                raise CheckpointStorageError(operation="read") from exc
            if record is None:
                return None
            self._check_binding(record, handle)
            if record.expires_at <= self.policy.now():
                return None
            return record

    def list_runs(self, thread_id: ThreadId | None = None) -> tuple[CheckpointSummary, ...]:
        """List active payload-free records in deterministic order."""
        with self._lock:
            connection = self._open_connection()
            query = "SELECT run_id, record_json FROM studio_checkpoints WHERE expires_at > ?"
            parameters: tuple[str, ...] = (self.policy.now().isoformat(),)
            if thread_id is not None:
                query += " AND thread_id = ?"
                parameters = (*parameters, str(thread_id))
            try:
                rows = _fetch_all(connection.execute(query, parameters))
            except sqlite3.DatabaseError as exc:
                raise CheckpointStorageError(operation="list") from exc
            records = [self._decode(row, None) for row in rows]
            summaries = [
                CheckpointSummary.from_record(record) for record in records if record is not None
            ]
            return tuple(
                sorted(
                    summaries,
                    key=lambda summary: (summary.updated_at, str(summary.handle.run_id)),
                    reverse=True,
                )
            )

    def delete_thread(self, thread_id: ThreadId) -> int:
        """Delete one thread in an immediate transaction."""
        with self._lock, self._transaction("delete") as connection:
            cursor = connection.execute(
                "DELETE FROM studio_checkpoints WHERE thread_id = ?", (str(thread_id),)
            )
            return cursor.rowcount

    def purge_expired(self) -> int:
        """Delete expired rows in an immediate transaction."""
        with self._lock, self._transaction("purge") as connection:
            cursor = connection.execute(
                "DELETE FROM studio_checkpoints WHERE expires_at <= ?",
                (self.policy.now().isoformat(),),
            )
            return cursor.rowcount


__all__ = [
    "CheckpointBindingError",
    "CheckpointClosedError",
    "CheckpointConfigurationError",
    "CheckpointCorruptionError",
    "CheckpointError",
    "CheckpointExpiredError",
    "CheckpointPolicy",
    "CheckpointRecord",
    "CheckpointSerializationError",
    "CheckpointStorageError",
    "CheckpointStore",
    "CheckpointSummary",
    "CheckpointVersionError",
    "CheckpointVersions",
    "JsonObject",
    "MemoryCheckpointStore",
    "RequestHash",
    "RunHandle",
    "RunId",
    "SQLiteCheckpointStore",
    "ThreadId",
]
