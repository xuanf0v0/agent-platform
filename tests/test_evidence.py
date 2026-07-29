"""Evidence hierarchy unit tests."""

from __future__ import annotations

from amazon_create.schemas.evidence import (
    EVIDENCE_POLICY,
    EvidenceSourceKind,
    EvidenceTier,
    FactRow,
    FactStatus,
    authorize_copy_claims,
    merge_fact_rows,
    tier_for_kind,
)


def test_tier_order() -> None:
    assert EvidenceTier.HYPOTHESIS < EvidenceTier.THIRD_PARTY_MCP
    assert EvidenceTier.THIRD_PARTY_MCP < EvidenceTier.PRODUCT_CONFIRMED
    assert EvidenceTier.PRODUCT_CONFIRMED < EvidenceTier.AMAZON_OFFICIAL
    assert tier_for_kind(EvidenceSourceKind.COMPETITOR_PUBLIC) == EvidenceTier.COMPETITOR_PUBLIC


def test_policy_has_seven_levels() -> None:
    assert len(EVIDENCE_POLICY.order_zh) == 7


def test_absolute_without_evidence_blocked() -> None:
    auth = authorize_copy_claims(
        title="Rust Proof Garden Mesh",
        item_highlights="Outdoor use",
        bullets=["Guaranteed forever"],
        ledger=(),
    )
    assert not auth.allowed
    assert auth.blocked_claims


def test_verified_product_allows_material_row() -> None:
    ledger = (
        FactRow(
            fact="material",
            value="galvanized steel",
            source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
            status=FactStatus.VERIFIED,
        ),
    )
    auth = authorize_copy_claims(
        title="Galvanized Steel Mesh Roll",
        item_highlights="Garden barrier",
        bullets=["Built for outdoor projects"],
        ledger=ledger,
    )
    assert auth.allowed


def test_mcp_cannot_replace_product_fact() -> None:
    product = FactRow(
        fact="gauge",
        value="19 gauge",
        source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
        status=FactStatus.VERIFIED,
    )
    mcp = FactRow(
        fact="gauge",
        value="23 gauge",
        source_kind=EvidenceSourceKind.THIRD_PARTY_MCP,
        status=FactStatus.VERIFIED,
    )
    rows = merge_fact_rows((product,), mcp)
    assert rows[0].value == "19 gauge"
