"""Apply seller clarification answers without touching cached research."""

import re
from dataclasses import dataclass
from typing import Final

from amazon_copy.automatic_models import ClarificationAnswer, EvidenceBundle
from amazon_copy.review.models import (
    ClarificationQuestion,
    EvidenceSource,
    FactClaim,
    ListingReviewReport,
)
from amazon_copy.schemas import SourceListingCopy

_EXACT_SUPPRESSION_FINDINGS: Final = frozenset(
    {"FACT_PRIORITY_CONFLICT", "FACT_QUANTITY_MISMATCH"}
)


@dataclass(frozen=True, slots=True)
class ClarificationResolution:
    """Source and evidence after applying all supplied seller decisions."""

    source: SourceListingCopy
    evidence: EvidenceBundle
    unanswered_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    """All state required to apply one clarification turn."""

    source: SourceListingCopy
    evidence: EvidenceBundle
    report: ListingReviewReport
    answers: tuple[ClarificationAnswer, ...]


def _remove_phrase(text: str, phrase: str) -> str:
    pattern = rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])"
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" ,;:-")


def _confirmed_claim_value(
    question: ClarificationQuestion,
    answer: ClarificationAnswer,
    remove_terms: list[str],
    replace_claim_keys: set[str],
) -> str:
    if question.finding_code == "ACCESSORY_COUNT_AMBIGUITY":
        remove_terms.extend(question.claim_terms)
        return answer.value.strip()
    if question.finding_code == "FACT_CONFLICT":
        replace_claim_keys.add(question.fact_key.casefold())
        selected = answer.value.strip().casefold()
        remove_terms.extend(
            term for term in question.claim_terms if term.casefold() not in selected
        )
        return answer.value.strip()
    return " ".join((*question.claim_terms, answer.value.strip()))


def resolve_clarifications(
    request: ClarificationRequest,
) -> ClarificationResolution:
    """Apply confirmations as priority-4 facts and removals as exact excisions."""
    by_code = {answer.question_code: answer for answer in request.answers}
    added_claims: list[FactClaim] = []
    remove_terms: list[str] = []
    replace_claim_keys: set[str] = set()
    remove_claim_keys: set[str] = set()
    suppressed_claims: set[tuple[str, str]] = set()
    unanswered: list[str] = []
    for question in request.report.clarification_questions:
        answer = by_code.get(question.code)
        if answer is None:
            unanswered.append(question.code)
            continue
        match answer.action:
            case "confirm":
                if question.finding_code in _EXACT_SUPPRESSION_FINDINGS:
                    remove_terms.extend(question.claim_terms)
                    suppressed_claims.update(
                        (
                            question.fact_key.casefold(),
                            " ".join(term.casefold().split()),
                        )
                        for term in question.claim_terms
                    )
                    continue
                claim_value = _confirmed_claim_value(
                    question,
                    answer,
                    remove_terms,
                    replace_claim_keys,
                )
                added_claims.append(
                    FactClaim(
                        key=question.fact_key,
                        value=claim_value,
                        source=EvidenceSource.PACKAGING_BOM_USER,
                        sku_scope="all",
                    )
                )
            case "remove":
                remove_terms.extend(question.claim_terms)
                if question.finding_code in _EXACT_SUPPRESSION_FINDINGS:
                    suppressed_claims.update(
                        (
                            question.fact_key.casefold(),
                            " ".join(term.casefold().split()),
                        )
                        for term in question.claim_terms
                    )
                elif question.finding_code == "FACT_CONFLICT":
                    remove_claim_keys.add(question.fact_key.casefold())
    title = request.source.title
    highlights = request.source.item_highlights
    bullets = list(request.source.bullets)
    for term in remove_terms:
        title = _remove_phrase(title, term) or title
        highlights = _remove_phrase(highlights, term)
        bullets = [
            _remove_phrase(bullet, term) or "Product detail from source" for bullet in bullets
        ]
    resolved_source = request.source.model_copy(
        update={"title": title, "item_highlights": highlights, "bullets": bullets}
    )
    retained_claims = tuple(
        claim
        for claim in request.evidence.user_claims
        if not (
            (
                claim.key.casefold() in replace_claim_keys | remove_claim_keys
                and claim.source >= EvidenceSource.PACKAGING_BOM_USER
            )
            or (
                claim.key.casefold(),
                " ".join(claim.value.casefold().split()),
            )
            in suppressed_claims
        )
    )
    resolved_evidence = request.evidence.model_copy(
        update={"user_claims": (*retained_claims, *added_claims)}
    )
    return ClarificationResolution(
        source=resolved_source,
        evidence=resolved_evidence,
        unanswered_codes=tuple(unanswered),
    )


__all__ = ["ClarificationRequest", "ClarificationResolution", "resolve_clarifications"]
