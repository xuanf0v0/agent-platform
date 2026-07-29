"""Deterministic source requirements and postflight fact authorization."""

import re
from typing import Final

from amazon_copy.review.claim_value_matching import (
    singular_fact_key as _singular_fact_key,
)
from amazon_copy.review.claim_value_matching import (
    value_matches as _value_matches,
)
from amazon_copy.review.fact_candidates import (
    FactCandidate,
    fact_candidates,
    fact_signatures,
    fact_tokens,
    normalized_fact_text,
)
from amazon_copy.review.models import (
    EvidenceSource,
    FactCategory,
    FactRequirement,
    ListingReviewRequest,
    ResolvedFact,
    ReviewFinding,
    ReviewPhase,
)
from amazon_copy.review.rules import finding

_AFFIRMATIVE_VALUES: Final = frozenset(
    {"1", "confirmed", "included", "present", "supported", "true", "verified", "yes"}
)


def _candidate_authorized(candidate: FactCandidate, fact: ResolvedFact) -> bool:
    if not _value_matches(candidate.text, fact):
        return False
    if candidate.category is not FactCategory.BOM:
        return True
    candidate_words = fact_tokens(candidate.text)
    evidence_words = fact_tokens(f"{fact.key} {fact.value}")
    return candidate_words <= evidence_words


def _requirement_authorized(
    requirement: FactRequirement,
    candidate: str,
    facts: tuple[ResolvedFact, ...],
) -> bool:
    allowed_keys = {
        _singular_fact_key(requirement.fact_key),
        *map(_singular_fact_key, requirement.key_aliases),
    }
    for fact in facts:
        if fact.source > EvidenceSource.AMAZON_FIRST_PARTY_DATA:
            continue
        if _singular_fact_key(fact.key) not in allowed_keys:
            continue
        if requirement.authorization_mode == "affirmative":
            if normalized_fact_text(fact.value) in _AFFIRMATIVE_VALUES or _value_matches(
                candidate, fact
            ):
                return True
            continue
        if _value_matches(candidate, fact):
            return True
    return False


def specialized_requirement_findings(
    request: ListingReviewRequest,
    facts: tuple[ResolvedFact, ...],
) -> tuple[ReviewFinding, ...]:
    """Require separate structured evidence for every matched profile claim.

    Emit **one finding per fact_key** (root-cause merge). When the same
    unauthorized claim appears in multiple fields, locate the finding on
    ``listing`` so reports do not cascade identical gates onto every bullet.
    """
    fields = (
        ("title", request.title),
        ("item_highlights", request.item_highlights),
        *(("bullets", bullet) for bullet in request.bullets),
    )
    findings: list[ReviewFinding] = []
    for requirement in request.fact_requirements:
        matches = tuple(
            dict.fromkeys(
                match.group(0).strip()
                for _field, text in fields
                for pattern in requirement.claim_patterns
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            )
        )
        unsupported = tuple(
            match for match in matches if not _requirement_authorized(requirement, match, facts)
        )
        if not unsupported:
            continue
        hit_fields = tuple(
            dict.fromkeys(
                field
                for field, text in fields
                if any(term.casefold() in text.casefold() for term in unsupported)
            )
        )
        # One root per fact_key: multi-field reuse → listing-level; single field → that field.
        located_field = hit_fields[0] if len(hit_fields) == 1 else "listing"
        if located_field == "listing":
            message = (
                f"Listing级专项事实缺少SKU结构化授权：{requirement.fact_key}"
                f"（跨{len(hit_fields)}个字段复用，先修事实源再改引用字段）"
            )
        else:
            message = f"专项事实缺少结构化授权：{requirement.fact_key}"
        findings.append(
            finding(
                "SPECIALIZED_FACT_UNVERIFIED",
                "BLOCK",
                located_field,
                message,
                requirement.evidence_needed,
            ).model_copy(
                update={
                    "claim_terms": unsupported,
                    "fact_key": requirement.fact_key,
                    "question_code": f"confirm_{requirement.code}",
                }
            )
        )
    return tuple(findings)


def unauthorized_new_fact_findings(
    request: ListingReviewRequest,
    facts: tuple[ResolvedFact, ...],
) -> tuple[ReviewFinding, ...]:
    """Block generated concrete facts absent from source and priority 1-5 evidence."""
    if request.phase is not ReviewPhase.POSTFLIGHT:
        return ()
    baseline = frozenset(request.baseline_fact_signatures)
    findings: list[ReviewFinding] = []
    for candidate in fact_candidates(request):
        if candidate.signature in baseline:
            continue
        if any(_candidate_authorized(candidate, fact) for fact in facts):
            continue
        findings.append(
            finding(
                "UNAUTHORIZED_NEW_FACT",
                "BLOCK",
                candidate.field,
                f"生成文案新增未授权{candidate.category.value}事实：{candidate.text}",
                "需要优先级1-5结构化产品证据",
            ).model_copy(
                update={
                    "claim_terms": (candidate.text,),
                    "fact_key": candidate.category.value,
                }
            )
        )
    return tuple(findings)


__all__ = [
    "fact_signatures",
    "specialized_requirement_findings",
    "unauthorized_new_fact_findings",
]
