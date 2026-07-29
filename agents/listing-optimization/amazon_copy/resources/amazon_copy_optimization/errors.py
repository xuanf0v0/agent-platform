"""Typed failures for packaged contract-resource integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, final

from typing_extensions import override


@unique
class ContractResourceErrorCode(StrEnum):
    """Stable failure codes exposed by the resource boundary."""

    DUPLICATE_RESOURCE = "duplicate_resource"
    HASH_MISMATCH = "hash_mismatch"
    INVALID_POLICY = "invalid_policy"
    INVALID_UTF8 = "invalid_utf8"
    MISSING_RESOURCE = "missing_resource"
    NON_MARKDOWN = "non_markdown"
    NOT_ALLOWLISTED = "not_allowlisted"
    RESOURCE_TOO_LARGE = "resource_too_large"


@dataclass(frozen=True, slots=True)
class ContractResourceErrorDetails:
    """Immutable optional measurements carried by a resource failure."""

    expected_sha256: str = ""
    actual_sha256: str = ""
    max_bytes: int = 0


_EMPTY_ERROR_DETAILS: Final = ContractResourceErrorDetails()


@final
class ContractResourceError(Exception):
    """Typed failure that remains mutable for CPython traceback metadata."""

    __slots__ = ("code", "details", "filename")

    code: ContractResourceErrorCode
    filename: str
    details: ContractResourceErrorDetails

    def __init__(
        self,
        code: ContractResourceErrorCode,
        filename: str = "",
        details: ContractResourceErrorDetails = _EMPTY_ERROR_DETAILS,
    ) -> None:
        """Initialize a safe typed error while leaving traceback state mutable."""
        self.code = code
        self.filename = filename
        self.details = details
        super().__init__(code.value, filename)

    @property
    def expected_sha256(self) -> str:
        """Return the expected digest when integrity verification failed."""
        return self.details.expected_sha256

    @property
    def actual_sha256(self) -> str:
        """Return the observed digest when integrity verification failed."""
        return self.details.actual_sha256

    @property
    def max_bytes(self) -> int:
        """Return the active size cap when bounded reading failed."""
        return self.details.max_bytes

    @override
    def __str__(self) -> str:
        """Render a safe message without untrusted resource content."""
        return f"contract resource {self.code.value}: {self.filename}"


__all__ = [
    "ContractResourceError",
    "ContractResourceErrorCode",
    "ContractResourceErrorDetails",
]
