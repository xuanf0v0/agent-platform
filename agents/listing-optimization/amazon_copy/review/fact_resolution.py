"""Evidence precedence, quantity extraction, and fact conflict review."""

import re
from collections import defaultdict
from typing import Final

from amazon_copy.review.models import (
    EvidenceSource,
    FactClaim,
    ListingReviewRequest,
    ResolvedFact,
    ReviewFinding,
)
from amazon_copy.review.rules import finding

_QUANTITY_KEYS: Final = frozenset({"count", "number", "pack count", "piece count", "quantity"})
_THIRD_PARTY_KEYS: Final = frozenset(
    {
        "competition",
        "cpc",
        "demand",
        "monthly_search_volume",
        "popularity",
        "product_count",
        "search_volume",
        "volume",
    }
)
_QUANTITY_PATTERNS: Final = (
    re.compile(
        r"^\s*(\d+)\s+(?!(?:inch(?:es)?|in|cm|mm|ft|feet|oz|lb|pounds?)\b)",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(\d+)[ -]?(?:count|pack|pieces?|pcs)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:pack|package|set)\s+of\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+(?:count|pack)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)[ -]?(?:pieces?|pcs)\b", re.IGNORECASE),
    re.compile(r"\b(?:pack|package|set)\s+of\s+(\d+)\b", re.IGNORECASE),
)
_GENERIC_FACT_TOKENS: Final = frozenset(
    {"all", "count", "number", "pack", "piece", "pieces", "quantity", "scope", "sku"}
)
_PLURAL_ES_MIN_LENGTH: Final = 6
_PLURAL_S_MIN_LENGTH: Final = 5
_ACCESSORY_TOKEN_MAX_DISTANCE: Final = 12
_FACT_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z]{3,}")
_CLAUSE_SEPARATOR_RE: Final = re.compile(
    r"(?:[.;!?]|\b(?:although|but|however|though|whereas|yet)\b)",
    re.IGNORECASE,
)
_NEGATIVE_CONSTRUCTION_RE: Final = re.compile(
    r"""
    \b(?:
        not(?!\s+only\b)
        |no
        |never
        |without
        |cannot
        |can't
        |isn't
        |aren't
        |doesn't
        |don't
        |lacks?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NEGATIVE_SUFFIX_RE: Final = re.compile(
    r"""
    ^\s*(?:
        (?:[-:?=]\s*)?no\s*$
        |[-:?=]\s*no\b
        |(?:[-:?=]\s*)?(?:(?:is|was|has|remains?)\s+)?not\s+
            (?:certified|confirmed|present|proven|supported|verified)\b
        |(?:[-:?=]\s*)?(?:(?:is|was)\s+)?
            (?:uncertified|unconfirmed|unproven|unsupported|unverified)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_AFFIRMATIVE_VALUES: Final = frozenset(
    {"1", "certified", "confirmed", "present", "supported", "true", "verified", "yes"}
)


def _singularize_fact_token(token: str) -> str:
    if token.endswith("es") and len(token) >= _PLURAL_ES_MIN_LENGTH:
        return token[:-2]
    if token.endswith("s") and len(token) >= _PLURAL_S_MIN_LENGTH:
        return token[:-1]
    return token


def _is_supported_accessory_count(
    count_match: re.Match[str],
    title: str,
    quantity_fact: ResolvedFact,
    resolved: tuple[ResolvedFact, ...],
) -> bool:
    candidate = count_match.group(1)
    for fact in resolved:
        if fact is quantity_fact or candidate not in re.findall(r"\d+", fact.value):
            continue
        fact_text = f"{fact.key} {fact.value}".casefold()
        raw_tokens = [match.group(0) for match in _FACT_TOKEN_RE.finditer(fact_text)]
        tokens = {
            _singularize_fact_token(token)
            for token in raw_tokens
            if token not in _GENERIC_FACT_TOKENS
        }
        for token in tokens:
            for match in re.finditer(re.escape(token), title):
                if match.end() <= count_match.start():
                    distance = count_match.start() - match.end()
                elif match.start() >= count_match.end():
                    distance = match.start() - count_match.end()
                else:
                    distance = 0
                if 0 <= distance <= _ACCESSORY_TOKEN_MAX_DISTANCE:
                    return True
    return False


def observed_quantity_values(
    title: str,
    quantity_fact: ResolvedFact,
    resolved: tuple[ResolvedFact, ...],
) -> set[str]:
    """Return title counts that refer to the primary product rather than accessories."""
    observed: set[str] = set()
    for pattern in _QUANTITY_PATTERNS:
        for match in pattern.finditer(title):
            if not _is_supported_accessory_count(
                match,
                title.casefold(),
                quantity_fact,
                resolved,
            ):
                observed.add(match.group(1))
    return observed


def _is_allowed_authority(claim: FactClaim) -> bool:
    if claim.source < EvidenceSource.THIRD_PARTY_PUBLIC_DATA:
        return True
    key = claim.key.casefold().strip()
    return key.startswith(("keyword", "market.")) or key in _THIRD_PARTY_KEYS


def resolve_facts(
    claims: tuple[FactClaim, ...],
) -> tuple[tuple[ResolvedFact, ...], tuple[ReviewFinding, ...]]:
    """Resolve highest-authority claims and reject untrusted product facts."""
    groups: dict[tuple[str, str], list[FactClaim]] = defaultdict(list)
    findings: list[ReviewFinding] = []
    for claim in claims:
        if _is_allowed_authority(claim):
            groups[(claim.key.casefold(), claim.sku_scope.casefold())].append(claim)
        else:
            findings.append(
                finding(
                    "THIRD_PARTY_FACT_REJECTED",
                    "WARN",
                    f"fact.{claim.key.casefold()}",
                    "第三方、竞品或写作假设不能证明产品、安全、性能或兼容性事实",
                )
            )
    resolved: list[ResolvedFact] = []
    for key, scope in sorted(groups):
        group = groups[(key, scope)]
        strongest = min(claim.source for claim in group)
        highest = [claim for claim in group if claim.source == strongest]
        values = {" ".join(claim.value.casefold().split()) for claim in highest}
        if len(values) > 1:
            findings.append(
                finding(
                    "FACT_CONFLICT",
                    "BLOCK",
                    f"fact.{key}",
                    f"同一优先级的产品事实冲突：{key}（SKU范围：{scope}）",
                    "请以包装、BOM、说明书、实测报告或用户确认消除冲突",
                ).model_copy(update={"claim_terms": tuple(sorted(values))})
            )
            continue
        selected = highest[0]
        resolved.append(
            ResolvedFact(
                key=selected.key,
                value=selected.value,
                source=selected.source,
                sku_scope=selected.sku_scope,
            )
        )
    return tuple(resolved), tuple(findings)


def supports_affirmative_term(
    facts: tuple[ResolvedFact, ...],
    term: str,
) -> bool:
    """Return whether strong structured evidence affirmatively supports one phrase."""
    normalized_term = " ".join(term.casefold().replace("_", " ").split())
    pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
        re.IGNORECASE,
    )
    for fact in facts:
        if fact.source > EvidenceSource.AMAZON_FIRST_PARTY_DATA:
            continue
        value = " ".join(fact.value.casefold().replace("_", " ").split())
        for match in pattern.finditer(value):
            clause_prefix = _CLAUSE_SEPARATOR_RE.split(value[: match.start()])[-1]
            suffix = value[match.end() :]
            if (
                _NEGATIVE_CONSTRUCTION_RE.search(clause_prefix) is None
                and _NEGATIVE_SUFFIX_RE.search(suffix) is None
            ):
                return True
        key = " ".join(fact.key.casefold().replace("_", " ").split())
        if pattern.fullmatch(key) is not None and value in _AFFIRMATIVE_VALUES:
            return True
    return False


def fact_priority_findings(
    request: ListingReviewRequest,
    resolved: tuple[ResolvedFact, ...],
) -> list[ReviewFinding]:
    """Find listing values superseded by stronger resolved evidence."""
    findings: list[ReviewFinding] = []
    full_text = " ".join((request.title, request.item_highlights, *request.bullets))
    folded = " ".join(full_text.casefold().split())
    for fact in resolved:
        key = fact.key.casefold()
        scope = fact.sku_scope.casefold()
        superseded = {
            " ".join(claim.value.casefold().split())
            for claim in request.claims
            if claim.key.casefold() == key
            and claim.sku_scope.casefold() == scope
            and claim.source > fact.source
            and claim.value.casefold() != fact.value.casefold()
        }
        conflicting_values = tuple(
            value
            for value in sorted(superseded)
            if not value.isdecimal()
            if re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", folded)
        )
        if conflicting_values:
            findings.append(
                finding(
                    "FACT_PRIORITY_CONFLICT",
                    "BLOCK",
                    f"fact.{key}",
                    f"文案采用了被更高优先级证据否定的事实：{'、'.join(conflicting_values)}",
                    f"必须使用优先级{fact.source.value}事实：{fact.value}",
                ).model_copy(update={"claim_terms": conflicting_values})
            )
        if key not in _QUANTITY_KEYS:
            continue
        expected = set(re.findall(r"\d+", fact.value))
        observed = observed_quantity_values(request.title, fact, resolved)
        wrong_counts = tuple(sorted(observed - expected, key=int))
        if wrong_counts and not conflicting_values:
            findings.append(
                finding(
                    "FACT_QUANTITY_MISMATCH",
                    "BLOCK",
                    f"fact.{key}",
                    f"文案数量与已解析权威事实不一致：{'、'.join(wrong_counts)}",
                    f"必须使用数量：{fact.value}",
                ).model_copy(update={"claim_terms": wrong_counts})
            )
    return findings


__all__ = ["fact_priority_findings", "resolve_facts", "supports_affirmative_term"]
