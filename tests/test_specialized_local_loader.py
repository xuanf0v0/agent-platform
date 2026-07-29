"""Local packaged specialized-rule agent node."""

from __future__ import annotations

from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.config import Settings
from amazon_copy.specialized_rules.catalog import Marketplace
from amazon_copy.specialized_rules.client import fetch_specialized_rules_sync
from amazon_copy.specialized_rules.local_loader import fetch_specialized_rules_local
from amazon_copy.specialized_rules.resource_loader import SpecializedRuleRequest
from amazon_copy.specialized_rules.routing import route_rule_profiles


def _request(product_type: str = "SWIM_VEST") -> SpecializedRuleRequest:
    route = route_rule_profiles(Marketplace.US, product_type)
    return SpecializedRuleRequest(
        source_fingerprint=source_fingerprint("Title: DRQ Toddler Floaties"),
        route=route,
    )


def test_local_loader_loads_swim_and_process_profiles_offline() -> None:
    outcome = fetch_specialized_rules_local(Settings(), request=_request())
    names = {snapshot.profile_filename for snapshot in outcome.cache.snapshots}

    assert outcome.cache.all_requested_loaded is True
    assert outcome.cache.gaps == ()
    assert "us-childrens-swim-aid-listing-audit.md" in names
    assert outcome.reused is False


def test_sync_client_defaults_to_local_when_mcp_unconfigured() -> None:
    settings = Settings(
        listing_optimize_mcp_url="",
        listing_optimize_mcp_token="",
    )
    outcome = fetch_specialized_rules_sync(settings, request=_request("SIGN_DISPLAY_STAND"))
    names = {snapshot.profile_filename for snapshot in outcome.cache.snapshots}

    assert outcome.cache.all_requested_loaded is True
    assert "us-adjustable-wedding-sign-stands.md" in names


def test_local_loader_reuses_source_bound_cache() -> None:
    settings = Settings()
    request = _request()
    first = fetch_specialized_rules_local(settings, request=request)
    second = fetch_specialized_rules_local(
        settings,
        request=request,
        cached=first.cache,
    )
    assert second.reused is True
    assert second.cache is first.cache
