"""Deterministic source rewrites that preserve only authorized product facts."""

import re
from typing import Final

from amazon_copy.automatic_models import EvidenceBundle
from amazon_copy.compliance.paste_ready import clamp_paste_ready_lengths
from amazon_copy.review.models import EvidenceSource, ListingReviewReport
from amazon_copy.review.search_terms import build_backend_search_terms
from amazon_copy.schemas import OptimizedListingCopy, SourceListingCopy

_AUTO_REMOVE_FINDINGS: Final = frozenset(
    {
        "OVERBROAD_COMPATIBILITY",
        "PRODUCT_CLASSIFICATION_UNRESOLVED",
        "PROMOTION_PRICE",
        "EXTERNAL_CONTACT",
        "REFUND_REVIEW",
        "SPECIALIZED_FACT_UNVERIFIED",
        "UNAUTHORIZED_NEW_FACT",
        "UNVERIFIED_PERFORMANCE",
        "UNVERIFIED_SAFETY",
    }
)
_SOURCE_AUTO_REMOVE_FACT_KEYS: Final = frozenset(
    {"heavy_duty", "rust_performance", "wind_performance"}
)
_ACCESSORY_AMBIGUITY_RE: Final = re.compile(
    r"\d+\s+leather\s+and\s+water\s+bags?",
    flags=re.IGNORECASE,
)
_LABEL_ONLY_RE: Final = re.compile(r"^(?:\[[^\]]+\]|[A-Z][A-Z0-9 &/-]{1,30})$")
_STRAP_KEYS: Final = frozenset({"included_straps", "strap_count", "strap_material", "strap_colors"})
_WATER_BAG_KEYS: Final = frozenset({"included_water_bags", "water_bag_count", "water_bags"})
_RESTRICTED_TITLE_CHARS: Final = str.maketrans("", "", "!$?_{}^¬¦")
_EMPTY_TERMS: Final[frozenset[str]] = frozenset()
_MIN_TRUNCATED_FALLBACK_LEN: Final = 24


def _remove_phrase(text: str, phrase: str) -> str:
    """Remove *phrase* from *text* case-insensitively.

    Prefers word-boundary-anchored regex so we don't clip mid-word.
    Falls back to substring removal when the regex cannot match — this
    handles fact-candidate texts (e.g. BOM patterns limited to 60 chars)
    that end mid-token and therefore fail the trailing word-boundary check.
    """
    pattern = rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])"
    if re.search(pattern, text, re.IGNORECASE):
        cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip(" ,.;:-")

    # Substring fallback is reserved for long extracted claim fragments. Short
    # terms such as ``stone`` or ``inc`` must never be removed from inside
    # legitimate words such as ``stones`` or ``inches``.
    if len(phrase.strip()) < _MIN_TRUNCATED_FALLBACK_LEN or " " not in phrase.strip():
        return text

    # A long phrase may be a truncated prefix of the actual listing text (e.g.
    # "...ages 2-" vs "...ages 2-6 Years Old").
    folded = text.casefold()
    needle = phrase.casefold()
    pos = folded.find(needle)
    if pos == -1:
        return text
    cleaned = text[:pos] + text[pos + len(needle):]
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(" ,.;:-")


def _confirmed_accessories(evidence: EvidenceBundle) -> tuple[str, str] | None:
    claims = tuple(
        claim
        for claim in evidence.user_claims
        if claim.source <= EvidenceSource.AMAZON_FIRST_PARTY_DATA
    )
    for strap in claims:
        if strap.key.casefold() not in _STRAP_KEYS:
            continue
        for water_bag in claims:
            if (
                water_bag.key.casefold() in _WATER_BAG_KEYS
                and water_bag.sku_scope.casefold() == strap.sku_scope.casefold()
            ):
                return strap.value, water_bag.value
    return None


def _output_removable_terms(report: ListingReviewReport) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            term
            for finding in report.findings
            if finding.code in _AUTO_REMOVE_FINDINGS
            for term in finding.claim_terms
        )
    )


def _source_removable_terms(report: ListingReviewReport) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            term
            for finding in report.findings
            if finding.code in _AUTO_REMOVE_FINDINGS
            and (
                finding.code == "UNVERIFIED_PERFORMANCE"
                or (
                    finding.code == "UNAUTHORIZED_NEW_FACT"
                    and finding.fact_key in {"bom", "compatibility"}
                )
                or finding.fact_key in _SOURCE_AUTO_REMOVE_FACT_KEYS
            )
            for term in finding.claim_terms
        )
    )


def _drop_bullet_terms(report: ListingReviewReport) -> frozenset[str]:
    return frozenset(
        term.casefold()
        for finding in report.findings
        if finding.fact_key == "compatibility"
        for term in finding.claim_terms
    )


def _remove_terms(
    title: str,
    highlights: str,
    bullets: list[str],
    terms: tuple[str, ...],
    drop_bullet_terms: frozenset[str] = _EMPTY_TERMS,
) -> tuple[str, str, list[str]]:
    bullets = [
        bullet
        for bullet in bullets
        if not any(term in bullet.casefold() for term in drop_bullet_terms)
    ]
    for term in terms:
        title = _remove_phrase(title, term)
        highlights = _remove_phrase(highlights, term)
        rewritten_bullets: list[str] = []
        for bullet in bullets:
            rewritten = _remove_phrase(bullet, term)
            rewritten_bullets.append(rewritten)
        bullets = rewritten_bullets
    return title, highlights, bullets


def _content_bullets(bullets: list[str]) -> list[str]:
    return [bullet for bullet in bullets if bullet and not _LABEL_ONLY_RE.fullmatch(bullet)]


def safely_rewrite_source(
    source: SourceListingCopy,
    report: ListingReviewReport,
    evidence: EvidenceBundle,
) -> SourceListingCopy:
    """Remove unsupported performance claims and resolve confirmed BOM ambiguity."""
    title, highlights, bullets = _remove_terms(
        source.title,
        source.item_highlights,
        list(source.bullets),
        _source_removable_terms(report),
    )

    accessories = _confirmed_accessories(evidence)
    if accessories is not None:
        title = _ACCESSORY_AMBIGUITY_RE.sub("Accessory Kit", title)
        highlights = _ACCESSORY_AMBIGUITY_RE.sub("Accessory Kit", highlights)
        bullets = [
            _ACCESSORY_AMBIGUITY_RE.sub("leather straps and water bags", bullet)
            for bullet in bullets
        ]
        strap_value, water_bag_value = accessories
        details = (f"Includes {strap_value}.", f"Includes {water_bag_value}.")
        existing = " ".join(bullets).casefold()
        bullets.extend(detail for detail in details if detail.casefold() not in existing)

    title, highlights = clamp_paste_ready_lengths(
        title or source.title,
        highlights or title or source.title,
    )
    return source.model_copy(
        update={
            "title": title or source.title,
            "item_highlights": highlights or title or source.title,
            "bullets": _content_bullets(bullets),
        }
    )


def safely_rewrite_output(
    listing: OptimizedListingCopy,
    report: ListingReviewReport,
    suppressed_claim_terms: tuple[str, ...] = (),
) -> OptimizedListingCopy:
    """Remove unsupported performance claims introduced during generation.

    Always passes the title through ``_remove_terms`` so ``_remove_phrase``
    (including its substring-fallback path) can excise truncated fact-candidate
    texts.  The previous ``contaminated_title`` shortcut cleared the title to
    ``""`` before removal, which meant the fallback ``title or highlights or
    listing.title`` reintroduced the original (still-contaminated) title.
    """
    title, highlights, bullets = _remove_terms(
        listing.title,
        listing.item_highlights,
        list(listing.bullets),
        tuple(dict.fromkeys((*_output_removable_terms(report), *suppressed_claim_terms))),
        _drop_bullet_terms(report),
    )
    title, highlights = clamp_paste_ready_lengths(title, highlights)
    title = title.translate(_RESTRICTED_TITLE_CHARS).strip()
    backend_search_terms = build_backend_search_terms(listing.backend_search_terms.split())
    return listing.model_copy(
        update={
            "title": title or highlights or listing.title,
            "item_highlights": highlights or title or listing.title,
            "bullets": _content_bullets(bullets),
            "backend_search_terms": backend_search_terms,
        }
    )


__all__ = ["safely_rewrite_output", "safely_rewrite_source"]
