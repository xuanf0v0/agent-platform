"""Bounded, hash-verified access to the packaged contract allowlist."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Final, Self

from amazon_copy.resources.amazon_copy_optimization.errors import (
    ContractResourceError,
    ContractResourceErrorCode,
    ContractResourceErrorDetails,
)
from amazon_copy.resources.amazon_copy_optimization.manifest import (
    CONTRACT_MANIFEST,
    ContractResource,
    ContractResourceKind,
)

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

PACKAGE_NAME: Final = "amazon_copy.resources.amazon_copy_optimization"
DEFAULT_MAX_RESOURCE_BYTES: Final = 64_000
_SHA256_HEX_LENGTH: Final = 64
_MARKDOWN_KINDS: Final = frozenset(
    {
        ContractResourceKind.SKILL,
        ContractResourceKind.PRODUCT_PROFILE,
        ContractResourceKind.PROCESS_PROFILE,
        ContractResourceKind.OUTPUT_TEMPLATE,
    }
)
_HEX_DIGITS: Final = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class LoadedContractMarkdown:
    """Verified Markdown paired with its immutable manifest entry."""

    resource: ContractResource
    markdown: str


def _validate_manifest(manifest: tuple[ContractResource, ...]) -> None:
    seen: set[str] = set()
    for resource in manifest:
        if resource.filename in seen:
            raise ContractResourceError(
                ContractResourceErrorCode.DUPLICATE_RESOURCE,
                resource.filename,
            )
        seen.add(resource.filename)
        posix_filename = PurePosixPath(resource.filename)
        windows_filename = PureWindowsPath(resource.filename)
        is_basename = (
            posix_filename.name == resource.filename and windows_filename.name == resource.filename
        )
        has_windows_drive_or_stream = bool(windows_filename.drive) or ":" in resource.filename
        if not is_basename or has_windows_drive_or_stream or not resource.filename:
            raise ContractResourceError(
                ContractResourceErrorCode.NOT_ALLOWLISTED,
                resource.filename,
            )
        if resource.kind in _MARKDOWN_KINDS and posix_filename.suffix.casefold() != ".md":
            raise ContractResourceError(
                ContractResourceErrorCode.NON_MARKDOWN,
                resource.filename,
            )
        valid_hash = (
            len(resource.sha256) == _SHA256_HEX_LENGTH and set(resource.sha256) <= _HEX_DIGITS
        )
        if not valid_hash:
            raise ContractResourceError(
                ContractResourceErrorCode.INVALID_POLICY,
                resource.filename,
            )


@dataclass(frozen=True, slots=True)
class ContractResourceLoader:
    """Read only allowlisted bytes with an early size cap and SHA-256 binding."""

    root: Traversable
    manifest: tuple[ContractResource, ...] = CONTRACT_MANIFEST
    max_resource_bytes: int = DEFAULT_MAX_RESOURCE_BYTES

    def __post_init__(self) -> None:
        """Validate policy and manifest metadata before any resource read."""
        if self.max_resource_bytes <= 0:
            raise ContractResourceError(ContractResourceErrorCode.INVALID_POLICY)
        _validate_manifest(self.manifest)

    @classmethod
    def from_package(cls) -> Self:
        """Create an offline loader from installed package resources."""
        return cls(root=files(PACKAGE_NAME))

    def read_bytes(self, resource: ContractResource) -> bytes:
        """Read one exact manifest member without materializing oversized input."""
        if resource not in self.manifest:
            raise ContractResourceError(
                ContractResourceErrorCode.NOT_ALLOWLISTED,
                resource.filename,
            )
        node = self.root.joinpath(*resource.relative_path.parts)
        if not node.is_file():
            raise ContractResourceError(
                ContractResourceErrorCode.MISSING_RESOURCE,
                resource.filename,
            )
        with node.open("rb") as stream:
            content = stream.read(self.max_resource_bytes + 1)
        if len(content) > self.max_resource_bytes:
            raise ContractResourceError(
                ContractResourceErrorCode.RESOURCE_TOO_LARGE,
                resource.filename,
                ContractResourceErrorDetails(max_bytes=self.max_resource_bytes),
            )
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != resource.sha256:
            raise ContractResourceError(
                ContractResourceErrorCode.HASH_MISMATCH,
                resource.filename,
                ContractResourceErrorDetails(
                    expected_sha256=resource.sha256,
                    actual_sha256=actual_sha256,
                ),
            )
        return content

    def read_markdown(self, resource: ContractResource) -> LoadedContractMarkdown:
        """Decode a verified Markdown resource without interpreting its contents."""
        if resource.kind not in _MARKDOWN_KINDS:
            raise ContractResourceError(
                ContractResourceErrorCode.NON_MARKDOWN,
                resource.filename,
            )
        try:
            markdown = self.read_bytes(resource).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContractResourceError(
                ContractResourceErrorCode.INVALID_UTF8,
                resource.filename,
            ) from error
        return LoadedContractMarkdown(resource=resource, markdown=markdown)

    def load_profile(self, filename: str) -> LoadedContractMarkdown:
        """Resolve a profile only by an exact filename in the immutable allowlist."""
        for resource in self.manifest:
            if resource.is_profile and resource.filename == filename:
                return self.read_markdown(resource)
        raise ContractResourceError(
            ContractResourceErrorCode.NOT_ALLOWLISTED,
            filename,
        )

    def load_all_profiles(self) -> tuple[LoadedContractMarkdown, ...]:
        """Load every verified profile in deterministic manifest order."""
        return tuple(
            self.read_markdown(resource) for resource in self.manifest if resource.is_profile
        )

    def validate_all(self) -> tuple[ContractResource, ...]:
        """Verify every packaged manifest member and return the validated entries."""
        for resource in self.manifest:
            _ = self.read_bytes(resource)
        return self.manifest


__all__ = [
    "DEFAULT_MAX_RESOURCE_BYTES",
    "PACKAGE_NAME",
    "ContractResourceLoader",
    "LoadedContractMarkdown",
]
