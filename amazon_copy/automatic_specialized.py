"""Specialized route clarification, profile cache loading, and safe context."""

from dataclasses import dataclass
from typing import assert_never

from amazon_copy.agents.product_type_classifier import resolve_product_type
from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    RuleContext,
)
from amazon_copy.config import Settings
from amazon_copy.review.models import ClarificationQuestion, FactRequirement
from amazon_copy.schemas import SourceListingCopy
from amazon_copy.specialized_rules import _exhaustiveness
from amazon_copy.specialized_rules.client import fetch_specialized_rules_sync
from amazon_copy.specialized_rules.guidance import (
    SpecializedRuleGuidance,
    guidance_from_snapshots,
)
from amazon_copy.specialized_rules.models import SpecializedRuleCache
from amazon_copy.specialized_rules.requirements import requirements_for_snapshots
from amazon_copy.specialized_rules.resource_loader import (
    ReadOnlyRuleResourcesClient,
    SpecializedRuleRequest,
)
from amazon_copy.specialized_rules.routing import (
    MarketplaceClarificationNeeded,
    ResolvedMarketplace,
    resolve_marketplace,
    route_rule_profiles,
)


@dataclass(frozen=True, slots=True)
class SpecializedAutomaticState:
    """One route/load outcome carried through clarification and generation."""

    marketplace: str | None
    product_type: str | None
    questions: tuple[ClarificationQuestion, ...]
    cache: SpecializedRuleCache | None
    cache_reused: bool
    requirements: tuple[FactRequirement, ...]
    guidance: tuple[SpecializedRuleGuidance, ...]


@dataclass(frozen=True, slots=True)
class SpecializedStateRequest:
    """Typed inputs for one specialized route and cache resolution."""

    source_text: str
    source: SourceListingCopy
    context: AutomaticOptimizationContext
    dependencies: AutomaticOptimizationDependencies


def _confirmed_value(context: AutomaticOptimizationContext, code: str) -> str | None:
    return next(
        (
            answer.value.strip()
            for answer in context.clarification_answers
            if answer.question_code == code and answer.action == "confirm"
        ),
        None,
    )


def _marketplace_question(
    clarification: MarketplaceClarificationNeeded,
) -> ClarificationQuestion:
    candidates = "/".join(item.value for item in clarification.candidates)
    return ClarificationQuestion(
        code="confirm_marketplace",
        finding_code="MARKETPLACE_UNRESOLVED",
        fact_key="marketplace",
        question_zh=f"请确认目标 Amazon 站点 ({candidates})。",
        evidence_needed="Seller Central 目标站点或卖家确认",
    )


def _product_type_question() -> ClarificationQuestion:
    return ClarificationQuestion(
        code="confirm_product_type",
        finding_code="PRODUCT_TYPE_UNRESOLVED",
        fact_key="product_type",
        question_zh="请确认此商品的 Amazon Product Type。",
        evidence_needed="Seller Central 类目或 Product Type 记录",
    )


def resolve_specialized_state(request: SpecializedStateRequest) -> SpecializedAutomaticState:
    """Resolve both routing questions before one source-bound profile load."""
    source_text = request.source_text
    source = request.source
    context = request.context
    dependencies = request.dependencies
    listing_text = " ".join((source.title, source.item_highlights, *source.bullets))
    explicit_marketplace = _confirmed_value(context, "confirm_marketplace")
    cached_marketplace = (
        context.rule_context.marketplace
        if context.rule_context is not None and context.rule_context.marketplace != "UNRESOLVED"
        else None
    )
    explicit_marketplace = explicit_marketplace or context.marketplace or cached_marketplace
    marketplace_resolution = _exhaustiveness.widen_variant(
        resolve_marketplace(listing_text, explicit_marketplace)
    )
    questions: list[ClarificationQuestion] = []
    match marketplace_resolution:
        case MarketplaceClarificationNeeded() as clarification:
            questions.append(_marketplace_question(clarification))
            marketplace = None
        case ResolvedMarketplace(marketplace=resolved):
            marketplace = resolved
        case _ as unexpected:
            assert_never(_exhaustiveness.reject_variant(unexpected))
    marketplace_code = marketplace.value if marketplace is not None else None
    product_type = (
        _confirmed_value(context, "confirm_product_type")
        or context.product_type
        or (
            context.rule_context.product_type
            if context.rule_context is not None
            and context.rule_context.product_type != "GENERAL_PRODUCT"
            else None
        )
    )
    if product_type and product_type.strip().upper() == "GENERAL_PRODUCT":
        product_type = None
    if not product_type:
        # Use settings-bound classifier role only — never the optimizer LLM client.
        product_type = resolve_product_type(
            source,
            marketplace=marketplace_code,
            settings=dependencies.settings,
        )
    if not product_type:
        questions.append(_product_type_question())
    if questions or marketplace is None or not product_type:
        return SpecializedAutomaticState(
            marketplace=marketplace.value if marketplace is not None else None,
            product_type=product_type,
            questions=tuple(questions),
            cache=None,
            cache_reused=False,
            requirements=(),
            guidance=(),
        )
    route = route_rule_profiles(marketplace, product_type)
    route_request = SpecializedRuleRequest(
        source_fingerprint=source_fingerprint(source_text),
        route=route,
    )
    settings = dependencies.settings or Settings()
    fetcher = dependencies.specialized_rule_fetcher or fetch_specialized_rules_sync
    try:
        loaded = fetcher(
            settings,
            request=route_request,
            cached=context.cached_specialized_rules,
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError, ExceptionGroup):
        loaded = ReadOnlyRuleResourcesClient.failure(route_request, "provider_error")
    snapshots = loaded.cache.snapshots
    return SpecializedAutomaticState(
        marketplace=marketplace.value,
        product_type=product_type,
        questions=(),
        cache=loaded.cache,
        cache_reused=loaded.reused,
        requirements=requirements_for_snapshots(snapshots),
        guidance=guidance_from_snapshots(snapshots),
    )


def apply_specialized_route(
    rules: RuleContext,
    state: SpecializedAutomaticState,
) -> RuleContext:
    """Align fallback limits with a resolved route without claiming authority."""
    marketplace = state.marketplace or rules.marketplace
    product_type = state.product_type or rules.product_type
    gaps = tuple(
        gap.model_copy(update={"marketplace": marketplace, "product_type": product_type})
        for gap in rules.gaps
        if not (gap.code == "marketplace_unresolved" and state.marketplace is not None)
        and not (gap.code == "product_type_unresolved" and state.product_type is not None)
    )
    return rules.model_copy(
        update={
            "marketplace": marketplace,
            "product_type": product_type,
            "rules": rules.rules.model_copy(
                update={"marketplace": marketplace, "product_type": product_type}
            ),
            "gaps": gaps,
        }
    )


__all__ = [
    "SpecializedAutomaticState",
    "SpecializedStateRequest",
    "apply_specialized_route",
    "resolve_specialized_state",
]
