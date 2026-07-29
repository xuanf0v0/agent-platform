"""Rule inference, evidence assembly, and review request construction."""

import hashlib

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    EvidenceBundle,
    RuleContext,
    RuleGap,
)
from amazon_copy.mcp.live_research_types import ResearchBundle
from amazon_copy.review.fact_candidates import fact_signatures
from amazon_copy.review.models import (
    EvidenceSource,
    FactClaim,
    FactRequirement,
    ListingReviewRequest,
    MarketplaceRules,
    ReviewPhase,
)
from amazon_copy.schemas import OptimizedListingCopy, SourceListingCopy
from amazon_copy.specialized_rules.routing import (
    SpecializedRuleRoutingResult,
    resolve_rule_route,
)


def source_fingerprint(source_text: str) -> str:
    """Hash source bytes with a length prefix for stale-cache rejection."""
    encoded = source_text.encode("utf-8")
    framed = len(encoded).to_bytes(8, "big") + encoded
    return hashlib.sha256(framed).hexdigest()


def infer_product_type(title: str) -> str | None:
    """Infer one stable product type from source identity terms (heuristic)."""
    from amazon_copy.specialized_rules.product_types import (  # noqa: PLC0415
        infer_product_type_heuristic,
    )

    return infer_product_type_heuristic(title)


def resolve_specialized_rule_route(
    source: SourceListingCopy,
    context: AutomaticOptimizationContext,
) -> SpecializedRuleRoutingResult:
    """Expose the automatic-pipeline seam for specialized profile routing."""
    answered_marketplace = next(
        (
            answer.value.strip()
            for answer in context.clarification_answers
            if answer.question_code == "confirm_marketplace" and answer.action == "confirm"
        ),
        None,
    )
    answered_product_type = next(
        (
            answer.value.strip()
            for answer in context.clarification_answers
            if answer.question_code == "confirm_product_type" and answer.action == "confirm"
        ),
        None,
    )
    product_type = answered_product_type or context.product_type or infer_product_type(source.title)
    marketplace = answered_marketplace or context.marketplace
    source_text = " ".join((source.title, source.item_highlights, *source.bullets))
    return resolve_rule_route(source_text, marketplace, product_type)


def resolve_rule_context(
    source: SourceListingCopy,
    context: AutomaticOptimizationContext,
) -> RuleContext:
    """Use supplied authoritative rules or explicit US fallback limits."""
    confirmed_product_type = next(
        (
            answer.value.strip()
            for answer in context.clarification_answers
            if answer.question_code == "confirm_product_type" and answer.action == "confirm"
        ),
        None,
    )
    confirmed_marketplace = next(
        (
            answer.value.strip().upper()
            for answer in context.clarification_answers
            if answer.question_code == "confirm_marketplace" and answer.action == "confirm"
        ),
        None,
    )
    if context.rule_context is not None:
        if confirmed_product_type is None and confirmed_marketplace is None:
            return context.rule_context
        cached = context.rule_context
        marketplace = confirmed_marketplace or cached.marketplace
        product_type = confirmed_product_type or cached.product_type
        return cached.model_copy(
            update={
                "marketplace": marketplace,
                "product_type": product_type,
                "rules": cached.rules.model_copy(
                    update={"marketplace": marketplace, "product_type": product_type}
                ),
                "gaps": tuple(
                    gap.model_copy(
                        update={"marketplace": marketplace, "product_type": product_type}
                    )
                    for gap in cached.gaps
                    if not (
                        gap.code == "product_type_unresolved" and confirmed_product_type is not None
                    )
                    and not (
                        gap.code == "marketplace_unresolved" and confirmed_marketplace is not None
                    )
                ),
            }
        )
    if context.rules is not None:
        return RuleContext(
            marketplace=context.rules.marketplace,
            product_type=context.rules.product_type,
            rules=context.rules,
            authoritative=True,
        )
    supplied_product_type = (context.product_type or "").strip()
    if supplied_product_type.casefold() == "general_product":
        supplied_product_type = ""
    inferred_product_type = supplied_product_type or infer_product_type(source.title)
    product_type = confirmed_product_type or inferred_product_type or "GENERAL_PRODUCT"
    marketplace = confirmed_marketplace or (context.marketplace or "").strip().upper()
    if not marketplace:
        marketplace = "UNRESOLVED"
    rules = MarketplaceRules(marketplace=marketplace, product_type=product_type)
    gaps = [
        RuleGap(
            code="authoritative_rules_missing",
            marketplace=marketplace,
            product_type=product_type,
        )
    ]
    if confirmed_product_type is None and inferred_product_type is None:
        gaps.append(
            RuleGap(
                code="product_type_unresolved",
                marketplace=marketplace,
                product_type=product_type,
            )
        )
    if confirmed_marketplace is None and not (context.marketplace or "").strip():
        gaps.append(
            RuleGap(
                code="marketplace_unresolved",
                marketplace=marketplace,
                product_type=product_type,
            )
        )
    return RuleContext(
        marketplace=marketplace,
        product_type=product_type,
        rules=rules,
        authoritative=False,
        gaps=tuple(gaps),
    )


def build_evidence_bundle(
    context: AutomaticOptimizationContext,
    research: ResearchBundle,
) -> EvidenceBundle:
    """Convert research keywords and market metrics into priority-6 claims.

    Keywords become ``keyword.N`` claims; metrics become ``market.<key>`` claims.
    Neither is product/safety authority — only SEO/market context.
    """
    research_claims = tuple(
        FactClaim(
            key=f"keyword.{index}",
            value=keyword,
            source=EvidenceSource.THIRD_PARTY_PUBLIC_DATA,
            sku_scope="all",
        )
        for index, keyword in enumerate(research.allowed_keywords, start=1)
    )
    metric_claims: list[FactClaim] = []
    seen_metric_keys: set[str] = set()
    for item in research.items:
        if item.kind != "market_metric":
            continue
        key = f"market.{item.key.casefold()}"
        if key in seen_metric_keys:
            continue
        seen_metric_keys.add(key)
        metric_claims.append(
            FactClaim(
                key=key,
                value=f"{item.value} ({item.provider}/{item.tool})",
                source=EvidenceSource.THIRD_PARTY_PUBLIC_DATA,
                sku_scope="all",
            )
        )
        if len(metric_claims) >= 16:
            break
    claims: list[FactClaim] = []
    seen_claims: set[tuple[str, str, EvidenceSource, str]] = set()
    for claim in (*context.user_claims, *research_claims, *metric_claims):
        identity = (claim.key, claim.value, claim.source, claim.sku_scope)
        if identity not in seen_claims:
            seen_claims.add(identity)
            claims.append(claim)
    allowed_keywords = tuple(dict.fromkeys((*context.allowed_keywords, *research.allowed_keywords)))
    return EvidenceBundle(
        user_claims=tuple(claims),
        suppressed_claim_terms=context.suppressed_claim_terms,
        research=research,
        allowed_keywords=allowed_keywords,
    )


def source_review_request(
    source: SourceListingCopy,
    rules: RuleContext,
    evidence: EvidenceBundle,
    fact_requirements: tuple[FactRequirement, ...] = (),
) -> ListingReviewRequest:
    """Build source-phase review input from resolved rule and evidence bundles."""
    return ListingReviewRequest(
        title=source.title,
        item_highlights=source.item_highlights,
        bullets=tuple(source.bullets),
        backend_search_terms=source.backend_search_terms,
        rules=rules.rules,
        claims=evidence.user_claims,
        fact_requirements=fact_requirements,
        primary_terms=evidence.allowed_keywords,
        phase=ReviewPhase.SOURCE,
    )


def postflight_review_request(
    listing: OptimizedListingCopy,
    rules: RuleContext,
    evidence: EvidenceBundle,
    source_request: ListingReviewRequest,
) -> ListingReviewRequest:
    """Build strict postflight review input from generated listing fields."""
    return ListingReviewRequest(
        title=listing.title,
        item_highlights=listing.item_highlights,
        bullets=tuple(listing.bullets),
        backend_search_terms=listing.backend_search_terms,
        rules=rules.rules,
        claims=evidence.user_claims,
        fact_requirements=source_request.fact_requirements,
        baseline_fact_signatures=fact_signatures(source_request),
        primary_terms=evidence.allowed_keywords,
        phase=ReviewPhase.POSTFLIGHT,
    )


__all__ = [
    "build_evidence_bundle",
    "infer_product_type",
    "postflight_review_request",
    "resolve_rule_context",
    "resolve_specialized_rule_route",
    "source_fingerprint",
    "source_review_request",
]
