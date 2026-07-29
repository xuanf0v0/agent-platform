"""Bounded discovery and parsing for allowlisted MCP rule resources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, assert_never
from urllib.parse import parse_qsl, unquote, urlsplit

import anyio
from mcp.types import (
    BlobResourceContents,
    ListResourcesResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
)

from amazon_copy.mcp.security import is_secret_key, sanitize_mcp_text
from amazon_copy.specialized_rules import _exhaustiveness
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES
from amazon_copy.specialized_rules.models import (
    RuleGapCode,
    SpecializedRuleCache,
    SpecializedRuleGap,
    SpecializedRuleLoad,
    SpecializedRuleSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import AnyUrl, SecretStr

    from amazon_copy.specialized_rules.routing import RuleRoute


class _ResourceSession(Protocol):
    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult: ...

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult: ...


@dataclass(frozen=True, slots=True)
class RuleReadPolicy:
    """Bounded resource-discovery and Markdown-read policy."""

    bearer_secret: SecretStr
    max_resource_bytes: int = 64_000
    max_pages: int = 16
    max_resources_per_page: int = 128
    max_total_resources: int = 256
    timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class SpecializedRuleRequest:
    """Source-bound request for one deterministic profile route."""

    source_fingerprint: str
    route: RuleRoute


@dataclass(frozen=True, slots=True)
class _ResourceCandidate:
    uri: AnyUrl


@dataclass(frozen=True, slots=True)
class _Discovery:
    candidates: Mapping[str, _ResourceCandidate]
    terminal_profiles: frozenset[str]
    gaps: tuple[SpecializedRuleGap, ...]


def _requested_profiles(request: SpecializedRuleRequest) -> tuple[str, ...]:
    return tuple(dict.fromkeys(profile.filename for profile in request.route.profiles))


def _gap(code: RuleGapCode, profile_filename: str = "") -> SpecializedRuleGap:
    return SpecializedRuleGap(code=code, profile_filename=profile_filename)


def _filename_from_uri(uri: AnyUrl) -> str:
    return unquote(urlsplit(str(uri)).path).rsplit("/", maxsplit=1)[-1]


def _uri_has_credentials(uri: AnyUrl) -> bool:
    try:
        parts = urlsplit(str(uri))
    except ValueError:
        return True
    query_keys = (key for key, _value in parse_qsl(parts.query, keep_blank_values=True))
    return (
        parts.username is not None
        or parts.password is not None
        or bool(parts.fragment)
        or any(is_secret_key(key) for key in query_keys)
    )


def _is_markdown(mime_type: str | None) -> bool:
    return (
        mime_type is not None and mime_type.partition(";")[0].strip().casefold() == "text/markdown"
    )


@dataclass(frozen=True, slots=True)
class ReadOnlyRuleResourcesClient:
    """MCP Resources adapter that exposes no tool-call operation."""

    session: _ResourceSession
    policy: RuleReadPolicy

    async def load(
        self,
        request: SpecializedRuleRequest,
        cached: SpecializedRuleCache | None = None,
    ) -> SpecializedRuleLoad:
        """Reuse an exact cache or discover and read one bounded profile route."""
        requested = _requested_profiles(request)
        if (
            cached is not None
            and cached.source_fingerprint == request.source_fingerprint
            and cached.route_fingerprint == request.route.fingerprint
            and cached.requested_profiles == requested
        ):
            return SpecializedRuleLoad(cache=cached, reused=True)
        try:
            with anyio.fail_after(self.policy.timeout_seconds):
                return await self._load_uncached(request)
        except TimeoutError:
            return self.failure(request, "provider_timeout")
        except (
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
            anyio.EndOfStream,
            ExceptionGroup,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return self.failure(request, "provider_error")

    @staticmethod
    def failure(
        request: SpecializedRuleRequest,
        code: RuleGapCode,
    ) -> SpecializedRuleLoad:
        """Build a redacted failure cache without provider exception text."""
        return SpecializedRuleLoad(
            cache=SpecializedRuleCache(
                source_fingerprint=request.source_fingerprint,
                route_fingerprint=request.route.fingerprint,
                requested_profiles=_requested_profiles(request),
                gaps=(_gap(code),),
            ),
            reused=False,
        )

    async def _load_uncached(
        self,
        request: SpecializedRuleRequest,
    ) -> SpecializedRuleLoad:
        discovery = await self._discover(request)
        requested = _requested_profiles(request)
        gaps = list(discovery.gaps)
        snapshots: list[SpecializedRuleSnapshot] = []
        for filename in requested:
            candidate = discovery.candidates.get(filename)
            if candidate is None:
                if filename not in discovery.terminal_profiles:
                    gaps.append(_gap("resource_missing", filename))
                continue
            variant = _exhaustiveness.widen_variant(await self._read(filename, candidate))
            match variant:
                case SpecializedRuleSnapshot() as snapshot:
                    snapshots.append(snapshot)
                case SpecializedRuleGap() as gap:
                    gaps.append(gap)
                case _ as unexpected:
                    assert_never(_exhaustiveness.reject_variant(unexpected))
        loaded = bool(requested) and not gaps and len(snapshots) == len(requested)
        return SpecializedRuleLoad(
            cache=SpecializedRuleCache(
                source_fingerprint=request.source_fingerprint,
                route_fingerprint=request.route.fingerprint,
                requested_profiles=requested,
                snapshots=tuple(snapshots),
                gaps=tuple(gaps),
                all_requested_loaded=loaded,
            ),
            reused=False,
        )

    async def _discover(self, request: SpecializedRuleRequest) -> _Discovery:
        requested = frozenset(_requested_profiles(request))
        candidates: dict[str, _ResourceCandidate] = {}
        terminal: set[str] = set()
        gaps: list[SpecializedRuleGap] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        resource_count = 0
        for _page_number in range(self.policy.max_pages):
            page = await self.session.list_resources(cursor)
            page_count = len(page.resources)
            if (
                page_count > self.policy.max_resources_per_page
                or resource_count + page_count > self.policy.max_total_resources
            ):
                return _Discovery(
                    candidates={},
                    terminal_profiles=requested,
                    gaps=(*gaps, _gap("resource_too_large")),
                )
            resource_count += page_count
            for resource in page.resources:
                filename = _filename_from_uri(resource.uri)
                if filename not in requested or filename not in ALLOWLISTED_PROFILE_FILENAMES:
                    continue
                failure = self._resource_failure(resource)
                if failure is not None:
                    _ = candidates.pop(filename, None)
                    terminal.add(filename)
                    gaps.append(_gap(failure, filename))
                    continue
                if filename in candidates or filename in terminal:
                    _ = candidates.pop(filename, None)
                    terminal.add(filename)
                    gaps.append(_gap("resource_malformed", filename))
                    continue
                candidates[filename] = _ResourceCandidate(uri=resource.uri)
            next_cursor = page.nextCursor
            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                gaps.append(_gap("pagination_cycle"))
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            gaps.append(_gap("pagination_limit"))
        return _Discovery(
            candidates=candidates,
            terminal_profiles=frozenset(terminal),
            gaps=tuple(gaps),
        )

    def _resource_failure(self, resource: Resource) -> RuleGapCode | None:
        if _uri_has_credentials(resource.uri):
            return "resource_credential_rejected"
        if not _is_markdown(resource.mimeType):
            return "resource_not_markdown"
        if resource.size is not None and resource.size < 0:
            return "resource_malformed"
        if resource.size is not None and resource.size > self.policy.max_resource_bytes:
            return "resource_too_large"
        return None

    async def _read(
        self,
        filename: str,
        candidate: _ResourceCandidate,
    ) -> SpecializedRuleSnapshot | SpecializedRuleGap:
        result = await self.session.read_resource(candidate.uri)
        contents = result.contents
        if len(contents) != 1:
            return _gap("resource_malformed", filename)
        variant = _exhaustiveness.widen_variant(contents[0])
        match variant:
            case TextResourceContents() as content:
                if str(content.uri) != str(candidate.uri) or not content.text.strip():
                    return _gap("resource_malformed", filename)
                if not _is_markdown(content.mimeType):
                    return _gap("resource_not_markdown", filename)
                if len(content.text.encode("utf-8")) > self.policy.max_resource_bytes:
                    return _gap("resource_too_large", filename)
                sanitized = sanitize_mcp_text(
                    content.text,
                    (self.policy.bearer_secret.get_secret_value(),),
                )
                return SpecializedRuleSnapshot(
                    profile_filename=filename,
                    content_markdown=sanitized,
                    content_sha256=hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
                )
            case BlobResourceContents():
                return _gap("resource_malformed", filename)
            case _ as unexpected:
                assert_never(_exhaustiveness.reject_variant(unexpected))


__all__ = [
    "ReadOnlyRuleResourcesClient",
    "RuleReadPolicy",
    "SpecializedRuleRequest",
]
