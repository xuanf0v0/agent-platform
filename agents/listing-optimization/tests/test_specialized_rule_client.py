from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import anyio
import pytest
from amazon_copy.specialized_rules.catalog import Marketplace, RuleProfile
from amazon_copy.specialized_rules.client import (
    ReadOnlyRuleResourcesClient,
    RuleReadPolicy,
    SpecializedRuleRequest,
)
from amazon_copy.specialized_rules.models import SpecializedRuleSnapshot
from amazon_copy.specialized_rules.routing import RuleRoute
from mcp.types import (
    ListResourcesResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
)
from pydantic import AnyUrl, SecretStr, ValidationError

if TYPE_CHECKING:
    from mcp.types import BlobResourceContents


class FakeResourceSession:
    def __init__(
        self,
        pages: dict[str | None, ListResourcesResult],
        reads: dict[str, ReadResourceResult],
    ) -> None:
        self.pages: dict[str | None, ListResourcesResult] = pages
        self.reads: dict[str, ReadResourceResult] = reads
        self.list_calls: list[str | None] = []
        self.read_calls: list[str] = []

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        self.list_calls.append(cursor)
        return self.pages[cursor]

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        key = str(uri)
        self.read_calls.append(key)
        return self.reads[key]


class HangingResourceSession:
    def __init__(self) -> None:
        self.list_calls: int = 0

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        del cursor
        self.list_calls += 1
        await anyio.sleep_forever()
        raise AssertionError

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        raise AssertionError(uri)


def _profile(filename: str) -> RuleProfile:
    return RuleProfile(
        filename=filename,
        marketplaces=(Marketplace.US,),
        product_types=("TEST_PRODUCT",),
        kind="product",
    )


def _request(source_fingerprint: str, *filenames: str) -> SpecializedRuleRequest:
    profiles = tuple(_profile(filename) for filename in filenames)
    return SpecializedRuleRequest(
        source_fingerprint=source_fingerprint,
        route=RuleRoute(
            marketplace=Marketplace.US,
            product_type="TEST_PRODUCT",
            profiles=profiles,
            fingerprint="test-route-fingerprint",
        ),
    )


def _resource(
    filename: str,
    *,
    mime_type: str = "text/markdown",
    size: int | None = None,
    uri: str | None = None,
) -> Resource:
    resource_uri = AnyUrl(uri or f"rules://listing-optimize/{filename}")
    return Resource(
        name=filename,
        uri=resource_uri,
        mimeType=mime_type,
        size=size,
    )


def _markdown(filename: str, text: str) -> ReadResourceResult:
    uri = AnyUrl(f"rules://listing-optimize/{filename}")
    contents: list[TextResourceContents | BlobResourceContents] = [
        TextResourceContents(uri=uri, mimeType="text/markdown", text=text)
    ]
    return ReadResourceResult(contents=contents)


@pytest.mark.asyncio
async def test_pagination_cycle_and_misleading_success_preserve_missing_gap() -> None:
    # Given: successful list responses that repeat a cursor and omit the requested profile.
    filename = "us-adjustable-wedding-sign-stands.md"
    session = FakeResourceSession(
        pages={
            None: ListResourcesResult(resources=[], nextCursor="repeat"),
            "repeat": ListResourcesResult(resources=[], nextCursor="repeat"),
        },
        reads={},
    )
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(bearer_secret=SecretStr("secret")),
    )

    # When: discovery terminates the cursor cycle.
    outcome = await client.load(_request("source-a", filename))

    # Then: transport success is not misreported as a loaded profile.
    assert outcome.cache.all_requested_loaded is False
    assert {gap.code for gap in outcome.cache.gaps} == {
        "pagination_cycle",
        "resource_missing",
    }
    assert session.list_calls == [None, "repeat"]


@pytest.mark.asyncio
async def test_pagination_page_cap_stops_unbounded_discovery() -> None:
    # Given: a provider that always advertises another discovery page.
    filename = "us-adjustable-wedding-sign-stands.md"
    session = FakeResourceSession(
        pages={None: ListResourcesResult(resources=[], nextCursor="page-2")},
        reads={},
    )
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(bearer_secret=SecretStr("secret"), max_pages=1),
    )

    # When: discovery consumes the configured page budget.
    outcome = await client.load(_request("source-a", filename))

    # Then: the client stops at one page and exposes both limit and missing gaps.
    assert {gap.code for gap in outcome.cache.gaps} == {
        "pagination_limit",
        "resource_missing",
    }
    assert session.list_calls == [None]


@pytest.mark.asyncio
async def test_source_and_route_bound_cache_reuses_only_exact_resume() -> None:
    # Given: one successfully loaded profile and its cache.
    filename = "us-adjustable-wedding-sign-stands.md"
    uri = f"rules://listing-optimize/{filename}"
    session = FakeResourceSession(
        pages={None: ListResourcesResult(resources=[_resource(filename)])},
        reads={uri: _markdown(filename, "# Stable rule")},
    )
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(bearer_secret=SecretStr("secret")),
    )
    request = _request("source-a", filename)
    first = await client.load(request)

    # When: exact and stale-source resumes present the same cache.
    exact = await client.load(request, cached=first.cache)
    stale = await client.load(_request("source-b", filename), cached=first.cache)

    # Then: exact resume performs no I/O while stale source is fetched again.
    assert exact.reused is True
    assert stale.reused is False
    assert session.list_calls == [None, None]
    assert session.read_calls == [uri, uri]


@pytest.mark.asyncio
async def test_hung_discovery_times_out_as_a_safe_gap() -> None:
    # Given: a session whose discovery never yields.
    filename = "us-adjustable-wedding-sign-stands.md"
    session = HangingResourceSession()
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(
            bearer_secret=SecretStr("timeout-secret"),
            timeout_seconds=0.01,
        ),
    )

    # When: the bounded read-only client loads the route.
    outcome = await client.load(_request("source-a", filename))

    # Then: timeout is explicit, redacted, and never presented as loaded guidance.
    assert outcome.cache.snapshots == ()
    assert [gap.code for gap in outcome.cache.gaps] == ["provider_timeout"]
    assert outcome.cache.all_requested_loaded is False
    assert session.list_calls == 1


def test_internal_snapshot_cannot_accept_fact_authority_or_claim_fields() -> None:
    # Given: an allowlisted Markdown snapshot hash.
    content = "# Internal requirement"
    digest = hashlib.sha256(content.encode()).hexdigest()

    # When: callers try to promote internal guidance into fact authority.
    with pytest.raises(ValidationError):
        _ = SpecializedRuleSnapshot.model_validate(
            {
                "profile_filename": "us-adjustable-wedding-sign-stands.md",
                "content_markdown": content,
                "content_sha256": digest,
                "can_authorize_facts": True,
            }
        )
    with pytest.raises(ValidationError):
        _ = SpecializedRuleSnapshot.model_validate(
            {
                "profile_filename": "us-adjustable-wedding-sign-stands.md",
                "content_markdown": content,
                "content_sha256": digest,
                "claims": [{"key": "material", "value": "metal"}],
            }
        )

    # Then: the only constructible snapshot remains non-authoritative internal guidance.
    snapshot = SpecializedRuleSnapshot(
        profile_filename="us-adjustable-wedding-sign-stands.md",
        content_markdown=content,
        content_sha256=digest,
    )
    assert snapshot.can_authorize_facts is False
    assert snapshot.authority == "internal_guidance"
