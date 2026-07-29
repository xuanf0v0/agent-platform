"""Listing optimization with bounded model-output repair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from amazon_copy.compliance.paste_ready import (
    PASTE_ITEM_HIGHLIGHTS_MAX,
    PASTE_TITLE_MAX,
)
from amazon_copy.optimizer_generation import (
    CompletionRequest,
    GenerationPreparation,
    build_user_payload,
    complete_listing,
    prepare_generation_context,
)
from amazon_copy.optimizer_policy import enforce_paste_ready_policy, paste_ready_errors
from amazon_copy.optimizer_runtime import SimpleOptimizerError, resolve_client
from amazon_copy.prompt_loader import load_prompt
from amazon_copy.review.rules import BULLET_TASK_COUNT, covered_bullet_tasks, duplicate_bullet_pairs
from amazon_copy.review.search_terms import build_backend_search_terms

if TYPE_CHECKING:
    from amazon_copy.config import Settings
    from amazon_copy.llm import LLMClient
    from amazon_copy.optimizer_generation import GenerationContext
    from amazon_copy.review.models import ListingReviewRequest
    from amazon_copy.schemas import OptimizedListingCopy, SourceListingCopy
    from amazon_copy.specialized_rules.guidance import SpecializedRuleGuidance

_FORMAT_INVALID_MSG = "模型返回格式无效, 请重试"
_MAX_QUALITY_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class OptimizerRequest:
    """Typed inputs for one evidence-bound listing optimization."""

    source: SourceListingCopy
    llm: LLMClient | None = None
    settings: Settings | None = None
    verified_facts: str | None = None
    review_request: ListingReviewRequest | None = None
    specialized_guidance: tuple[SpecializedRuleGuidance, ...] = ()
    suppressed_claim_terms: tuple[str, ...] = ()
    research_context: dict[str, object] | None = None
    source_review_summary: dict[str, object] | None = None
    diagnosis_summary: dict[str, object] | None = None
    original_source_text: str = ""
    writing_analysis: dict[str, object] | None = None
    quality_feedback: str | None = None
    strict_quality_loop: bool = False


def _with_search_terms(
    listing: OptimizedListingCopy,
    context: GenerationContext,
) -> OptimizedListingCopy:
    terms = context.allowed_keywords or tuple(listing.backend_search_terms.split())
    backend_search_terms = build_backend_search_terms(
        terms,
        max_bytes=context.search_terms_max_bytes,
    )
    return listing.model_copy(update={"backend_search_terms": backend_search_terms})


def _first_validation_feedback(expected: int) -> str:
    return "".join(
        (
            "The prior response did not match the required JSON contract. ",
            "Return a JSON object with nonblank title and item_highlights plus exactly ",
            f"{expected} nonblank bullets. Use only source facts.",
        )
    )


def _paste_validation_feedback(errors: list[str], expected: int, has_facts: bool) -> str:
    fact_suffix = " and verified_facts." if has_facts else "."
    return "".join(
        (
            "The prior response failed paste-ready listing checks. ",
            "Fix these issues and return a JSON object with nonblank title ",
            "and item_highlights plus exactly ",
            f"{expected} nonblank bullets. Hard limits: title plain length {PASTE_TITLE_MAX} max; ",
            f"item_highlights plain length {PASTE_ITEM_HIGHLIGHTS_MAX} max. ",
            "Never use dual-tone, wind-resistant, anti-rust, or similar banned claim phrases. ",
            "Use only source facts",
            fact_suffix,
            " Errors: ",
            "; ".join(errors),
        )
    )


def _structural_quality_issues(
    listing: OptimizedListingCopy,
    expected_bullets: int,
) -> list[str]:
    """Check bullet structure, labels, duplicates, and task coverage.

    Deterministic checks that catch common LLM output defects without an
    extra model call.  Returns a list of human-readable issue strings.
    """
    issues: list[str] = []

    # Bullet count
    if len(listing.bullets) != expected_bullets:
        issues.append(
            f"Expected {expected_bullets} bullets, got {len(listing.bullets)}."
        )

    # Label presence and completeness
    for index, bullet in enumerate(listing.bullets, start=1):
        text = bullet.strip()
        colon_pos = text.find(":")
        if colon_pos == -1:
            issues.append(
                f"Bullet {index} lacks a benefit-led label (missing colon). "
                "Start with a 3-7 word Title Case label followed by ':'."
            )
        elif colon_pos == len(text) - 1:
            issues.append(f"Bullet {index} is label-only with no content after the colon.")
        else:
            label = text[:colon_pos].strip()
            body = text[colon_pos + 1:].strip()
            label_words = label.split()
            if len(label_words) > 8:
                issues.append(
                    f"Bullet {index} label is too long ({len(label_words)} words); "
                    "keep labels to 3-7 words."
                )
            if not body:
                issues.append(f"Bullet {index} has an empty body after the label.")

    # Duplicate detection
    pairs = duplicate_bullet_pairs(tuple(listing.bullets))
    for left, right in pairs:
        issues.append(
            f"Bullet {left} and Bullet {right} have high lexical overlap "
            "(duplicate content). Give each bullet one distinct intent."
        )

    # Bullet task coverage
    covered = covered_bullet_tasks(tuple(listing.bullets))
    if len(covered) < 3:
        issues.append(
            f"Bullets cover only {len(covered)} of {BULLET_TASK_COUNT} shopper "
            f"decision tasks ({', '.join(covered) or 'none'}). Aim for at least "
            "3 distinct intents: pack/identity, method, scenes, projects, care."
        )

    return issues


def _structural_quality_feedback(issues: list[str], expected: int) -> str:
    return "".join(
        (
            "The prior response has structural quality issues. ",
            "Fix these and return a JSON object with nonblank title and ",
            "item_highlights plus exactly ",
            f"{expected} nonblank bullets. Each bullet must start with a ",
            "clear benefit-led label (3-7 words, Title Case) followed by a ",
            "colon and a complete sentence. Give each bullet one distinct ",
            "shopper intent. Issues: ",
            "; ".join(issues),
        )
    )


def _all_quality_feedback(
    paste_errors: list[str],
    structural_issues: list[str],
    expected: int,
    has_facts: bool,
) -> str:
    sections: list[str] = []
    if paste_errors:
        sections.append(_paste_validation_feedback(paste_errors, expected, has_facts))
    if structural_issues:
        sections.append(_structural_quality_feedback(structural_issues, expected))
    return " ".join(sections)


def optimize_listing(
    source: SourceListingCopy,
    *,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
    verified_facts: str | None = None,
    review_request: ListingReviewRequest | None = None,
) -> OptimizedListingCopy:
    """Optimize one listing with bounded format and paste-ready repair."""
    return optimize_listing_request(
        OptimizerRequest(
            source=source,
            llm=llm,
            settings=settings,
            verified_facts=verified_facts,
            review_request=review_request,
        )
    )


def optimize_listing_request(request: OptimizerRequest) -> OptimizedListingCopy:
    """Optimize one typed request with bounded repair and fact context."""
    client = resolve_client(request.llm, request.settings)
    context = prepare_generation_context(
        GenerationPreparation(
            source=request.source,
            review_request=request.review_request,
            verified_facts=request.verified_facts,
            specialized_guidance=request.specialized_guidance,
            suppressed_claim_terms=request.suppressed_claim_terms,
            research_context=request.research_context,
            source_review_summary=request.source_review_summary,
            diagnosis_summary=request.diagnosis_summary,
            original_source_text=request.original_source_text,
            writing_analysis=request.writing_analysis,
        )
    )
    system = f"{load_prompt('constitution')}\n\n---\n{load_prompt('listing_optimizer')}"
    try:
        result = complete_listing(
            client,
            CompletionRequest(
                system=system,
                user=build_user_payload(
                    request.source,
                    context,
                    request.quality_feedback,
                ),
                temperature=0.2,
                expected_bullets=context.expected_bullets,
            ),
        )
    except ValueError:
        try:
            result = complete_listing(
                client,
                CompletionRequest(
                    system=system,
                    user=build_user_payload(
                        request.source,
                        context,
                        _first_validation_feedback(context.expected_bullets),
                    ),
                    temperature=0.1,
                    expected_bullets=context.expected_bullets,
                ),
            )
        except ValueError as exc:
            raise SimpleOptimizerError(_FORMAT_INVALID_MSG) from exc
    allow_weighted_base = context.allow_weighted_base
    last_issues: list[str] = []
    max_attempts = _MAX_QUALITY_ATTEMPTS if request.strict_quality_loop else 2
    for attempt in range(1, max_attempts + 1):
        result = enforce_paste_ready_policy(
            result, allow_weighted_base=allow_weighted_base
        )
        paste_errors = paste_ready_errors(
            result, allow_weighted_base=allow_weighted_base
        )
        structural_issues = (
            _structural_quality_issues(result, context.expected_bullets)
            if request.strict_quality_loop
            else []
        )
        last_issues = [*paste_errors, *structural_issues]
        if not last_issues:
            return _with_search_terms(result, context)
        if attempt == max_attempts:
            break
        try:
            result = complete_listing(
                client,
                CompletionRequest(
                    system=system,
                    user=build_user_payload(
                        request.source,
                        context,
                        _all_quality_feedback(
                            paste_errors,
                            structural_issues,
                            context.expected_bullets,
                            bool(context.facts),
                        ),
                    ),
                    temperature=0.1,
                    expected_bullets=context.expected_bullets,
                ),
            )
        except ValueError:
            continue

    prefix = (
        f"质量校验在 {max_attempts} 轮后仍未全部通过"
        if request.strict_quality_loop
        else "可粘贴校验未通过"
    )
    raise SimpleOptimizerError(prefix + ": " + "; ".join(last_issues[:5]))


__all__ = ["OptimizerRequest", "optimize_listing", "optimize_listing_request"]
