r"""Plain-text length (R1) and KW/RW unique hit counters (R3).

Matching rules (v1 EN):
- Case-insensitive via ``str.casefold``.
- Single-token terms use ASCII whole-word boundaries (``\\b``).
- Multi-word terms match as casefold substrings with word boundaries on both
  ends when possible (so ``usb hub`` hits in ``Best USB Hub kit`` but not
  mid-token junk like ``xusb hubx``).
- Terms are tried longest-first so multi-word phrases are preferred when
  ordering hit lists; each distinct list item is recorded at most once
  (presence, not multiplicity).
- Markdown bold markers ``**`` / ``__`` are stripped before measuring or
  matching so ``**usb** hub`` plain-matches ``usb``.

CJK / non-English: v1 always uses word-boundary EN rules. Substring-only
matching for CJK locales is deferred until locale configuration lands.
"""

from __future__ import annotations

import re
from typing import Final, TypedDict

_MD_BOLD_MARKERS: Final[tuple[str, ...]] = ("**", "__")


class KwRwFloorDetail(TypedDict):
    """Structured result of aggregate KW/RW floor checks."""

    kw_hits: list[str]
    rw_hits: list[str]
    kw_count: int
    rw_count: int
    kw_ok: bool
    rw_ok: bool
    min_kw: int
    min_rw: int


def strip_md_bold(text: str) -> str:
    """Strip ``**`` / ``__`` markers so length matches Amazon plain paste (R1)."""
    out = text
    for marker in _MD_BOLD_MARKERS:
        out = out.replace(marker, "")
    return out


def plain_len(text: str) -> int:
    """Unicode code-point length after stripping markdown bold markers (R1)."""
    return len(strip_md_bold(text))


def _term_pattern(term_cf: str) -> re.Pattern[str]:
    """Compile a casefold-ready pattern for a single or multi-word term."""
    parts = term_cf.split()
    if len(parts) == 1:
        # ASCII whole-token boundary for single tokens.
        return re.compile(rf"\b{re.escape(parts[0])}\b", flags=re.ASCII)
    # Multi-word: escaped tokens joined by whitespace, with outer \b when possible.
    body = r"\s+".join(re.escape(p) for p in parts)
    return re.compile(rf"\b{body}\b", flags=re.ASCII)


def _normalized_terms(terms: list[str]) -> list[str]:
    """Deduplicate terms preserving first-seen original form; drop empties."""
    seen_cf: set[str] = set()
    ordered: list[str] = []
    for raw in terms:
        term = raw.strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen_cf:
            continue
        seen_cf.add(key)
        ordered.append(term)
    return ordered


def find_unique_hits(text: str, terms: list[str]) -> list[str]:
    """Return unique terms present in *text* (case-insensitive, longest-first).

    Multiplicity is ignored: each distinct list item appears at most once.
    Hit order follows longest-first match order among present terms.
    """
    plain_cf = strip_md_bold(text).casefold()
    unique_terms = _normalized_terms(terms)
    # Longest-first so multi-word phrases are preferred in hit order.
    by_length = sorted(unique_terms, key=lambda t: len(t.casefold()), reverse=True)
    hits: list[str] = []
    for term in by_length:
        pattern = _term_pattern(term.casefold())
        if pattern.search(plain_cf) is not None:
            hits.append(term)
    return hits


def count_unique_hits(text: str, terms: list[str]) -> int:
    """Count distinct terms present in *text* (R3 unique presence)."""
    return len(find_unique_hits(text, terms))


def aggregate_hits_across_texts(texts: list[str], terms: list[str]) -> list[str]:
    """Union of unique term hits across multiple texts (e.g. 5 BPs combined).

    Used for aggregate floors: ≥20 RW / ≥10 KW across all bullet points.
    """
    plain_joined = " ".join(strip_md_bold(t) for t in texts)
    return find_unique_hits(plain_joined, terms)


def meets_kw_rw_floors(
    texts: list[str],
    keywords: list[str],
    rootwords: list[str],
    min_kw: int = 10,
    min_rw: int = 20,
) -> tuple[bool, KwRwFloorDetail]:
    """Check aggregate unique KW/RW floors across *texts* (default ≥10 / ≥20).

    Returns ``(ok, detail)`` where *detail* lists hits and counts for SEO tables.
    """
    kw_hits = aggregate_hits_across_texts(texts, keywords)
    rw_hits = aggregate_hits_across_texts(texts, rootwords)
    kw_count = len(kw_hits)
    rw_count = len(rw_hits)
    kw_ok = kw_count >= min_kw
    rw_ok = rw_count >= min_rw
    detail: KwRwFloorDetail = {
        "kw_hits": kw_hits,
        "rw_hits": rw_hits,
        "kw_count": kw_count,
        "rw_count": rw_count,
        "kw_ok": kw_ok,
        "rw_ok": rw_ok,
        "min_kw": min_kw,
        "min_rw": min_rw,
    }
    return kw_ok and rw_ok, detail
