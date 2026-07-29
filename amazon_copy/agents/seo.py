"""Pure Amazon SEO presence checks with optional narrative attachment.

V/X truth is deliberately independent of an LLM. This module uses the same
R1/R3 normalisation and matching implementation as all other product metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.schemas import EmbedRow, SEOCheck
from amazon_copy.utils.text_metrics import find_unique_hits

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from amazon_copy.schemas import ListingDraft


def _unique_terms(terms: Iterable[str]) -> list[str]:
    """Strip and case-insensitively deduplicate terms in caller order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in terms:
        term = " ".join(raw.split())
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result


def _rows(text: str, terms: Sequence[str]) -> list[EmbedRow]:
    """Build rows in supplied term order using deterministic text metrics."""
    unique = _unique_terms(terms)
    hit_keys = {term.casefold() for term in find_unique_hits(text, unique)}
    return [EmbedRow(item=term, present=term.casefold() in hit_keys) for term in unique]


def check_seo(  # noqa: PLR0913 - three independent term tables are the public contract
    title: str,
    bullets: Sequence[str],
    intents: Sequence[str],
    rootwords: Sequence[str],
    keywords: Sequence[str],
    *,
    narrative: str | None = None,
) -> SEOCheck:
    """Return title, BP, and combined V/X tables without calling an LLM.

    Bullet text is joined only for unique aggregate presence; multiplicity
    never contributes to counts. Narrative is stored verbatim and is never
    read while computing rows.
    """
    bullet_text = " ".join(bullets)
    combined_text = " ".join(part for part in (title, bullet_text) if part)
    return SEOCheck(
        intent_rows=_rows(combined_text, intents),
        rootword_rows=_rows(combined_text, rootwords),
        keyword_rows=_rows(combined_text, keywords),
        title_intent_rows=_rows(title, intents),
        title_rootword_rows=_rows(title, rootwords),
        title_keyword_rows=_rows(title, keywords),
        bullet_intent_rows=_rows(bullet_text, intents),
        bullet_rootword_rows=_rows(bullet_text, rootwords),
        bullet_keyword_rows=_rows(bullet_text, keywords),
        narrative=narrative,
    )


build_seo_check = check_seo


def check_listing_seo(
    listing: ListingDraft,
    intents: Sequence[str],
    rootwords: Sequence[str],
    keywords: Sequence[str],
    *,
    narrative: str | None = None,
) -> SEOCheck:
    """Convenience adapter for the domain ``ListingDraft`` model."""
    return check_seo(
        title=listing.title,
        bullets=[bullet.text for bullet in listing.bullets],
        intents=intents,
        rootwords=rootwords,
        keywords=keywords,
        narrative=narrative,
    )


__all__ = ["build_seo_check", "check_listing_seo", "check_seo"]
