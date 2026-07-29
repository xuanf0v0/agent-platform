"""Deterministic field, claim, bullet, and search-term checks."""

import re
from typing import Final

from amazon_copy.review.fact_resolution import supports_affirmative_term
from amazon_copy.review.models import (
    ListingReviewRequest,
    ResolvedFact,
    ReviewFinding,
    VariationRole,
)
from amazon_copy.review.rules import (
    COMPATIBILITY_TERMS,
    PERFORMANCE_TERMS,
    PROMO_TERMS,
    REFUND_REVIEW_TERMS,
    SAFETY_TERMS,
    contains_any,
    external_contact_claims,
    finding,
    has_external_contact,
    has_price,
    price_claims,
    title_is_incomplete,
    title_repeated_content_words,
    written_numbers,
)
from amazon_copy.review.search_terms import (
    BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES,
    search_term_duplication_pct,
    unverified_search_term_claims,
)
from amazon_copy.utils.text_metrics import plain_len

_RESTRICTED_TITLE_CHARS: Final = frozenset("!$?_{}^¬¦")
_UNNATURAL_PHRASES: Final = (
    "pcs large",
    "inches smooth",
    "large rock paintings",
    "oil paintings",
    "acrylic plates",
)
_ACCESSORY_AMBIGUITY_RE: Final = re.compile(
    r"\d+\s+leather\s+and\s+water\s+bags?",
    re.IGNORECASE,
)
_WATER_CLASSIFICATION_TERMS: Final = ("swim vest", "life jacket", "flotation vest")

# IH budget utilisation thresholds for the information-density check.
_HIGHLIGHTS_DENSITY_WARN_PCT: Final = 0.30  # warn when IH uses < 30% of budget
_HIGHLIGHTS_DENSITY_WARN_CHARS: Final = 50  # and is below this absolute floor

# Backend search-term duplication warning threshold.
_SEARCH_TERM_DUPLICATION_WARN_PCT: Final = 50.0


def field_findings(request: ListingReviewRequest) -> list[ReviewFinding]:
    """Check marketplace field limits and title structure."""
    findings: list[ReviewFinding] = []
    rules = request.rules
    if plain_len(request.title) > rules.title_max:
        findings.append(
            finding("TITLE_LENGTH", "BLOCK", "title", f"标题超过{rules.title_max}字符硬限制")
        )
    if request.item_highlights and plain_len(request.item_highlights) > rules.item_highlights_max:
        findings.append(
            finding(
                "HIGHLIGHTS_LENGTH",
                "BLOCK",
                "item_highlights",
                f"Item Highlights超过{rules.item_highlights_max}字符硬限制",
            )
        )
    search_terms_max_bytes = min(
        rules.backend_search_terms_max_bytes,
        BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES,
    )
    if len(request.backend_search_terms.encode("utf-8")) > search_terms_max_bytes:
        findings.append(
            finding(
                "SEARCH_TERMS_BYTES",
                "BLOCK",
                "backend_search_terms",
                f"Backend Search Terms超过{search_terms_max_bytes} UTF-8字节",
            )
        )
    if title_is_incomplete(request.title):
        findings.append(finding("TITLE_FRAGMENT", "BLOCK", "title", "标题以残缺片段结尾"))
    repeated = title_repeated_content_words(request.title)
    if repeated:
        findings.append(
            finding(
                "TITLE_WORD_REPETITION",
                "WARN",
                "title",
                "标题实词重复超过2次：" + "、".join(repeated),
            )
        )
    spelled = written_numbers(request.title)
    if spelled:
        findings.append(
            finding(
                "TITLE_WRITTEN_NUMBER",
                "WARN",
                "title",
                "标题数字优先使用阿拉伯数字：" + "、".join(spelled),
            )
        )
    restricted = tuple(char for char in request.title if char in _RESTRICTED_TITLE_CHARS)
    if restricted:
        findings.append(
            finding(
                "TITLE_RESTRICTED_CHAR",
                "BLOCK",
                "title",
                "标题包含限制字符：" + " ".join(dict.fromkeys(restricted)),
            )
        )
    if request.variation_role is VariationRole.PARENT:
        hits = contains_any(request.title, request.child_only_terms)
        if hits:
            findings.append(
                finding(
                    "PARENT_CHILD_SPEC",
                    "BLOCK",
                    "title",
                    "父体标题包含子体独有规格：" + "、".join(hits),
                )
            )
    return findings


def _located_claim_finding(
    code: str,
    field: str,
    message: str,
    evidence: str,
    terms: tuple[str, ...],
) -> ReviewFinding:
    return finding(code, "BLOCK", field, message, evidence).model_copy(
        update={"claim_terms": terms}
    )


def content_findings(
    request: ListingReviewRequest,
    resolved: tuple[ResolvedFact, ...],
) -> list[ReviewFinding]:
    """Check prohibited copy and evidence-dependent claims."""
    findings: list[ReviewFinding] = []
    full_text = " ".join((request.title, request.item_highlights, *request.bullets))
    promotional_terms = (*contains_any(full_text, PROMO_TERMS), *price_claims(full_text))
    if promotional_terms or has_price(full_text):
        findings.append(
            finding("PROMOTION_PRICE", "BLOCK", "listing", "包含促销、排名或价格信息").model_copy(
                update={"claim_terms": promotional_terms}
            )
        )
    if contains_any(full_text, REFUND_REVIEW_TERMS):
        findings.append(
            finding("REFUND_REVIEW", "BLOCK", "bullets", "包含退款、保证或索评表述").model_copy(
                update={"claim_terms": contains_any(full_text, REFUND_REVIEW_TERMS)}
            )
        )
    if has_external_contact(full_text):
        findings.append(
            finding("EXTERNAL_CONTACT", "BLOCK", "bullets", "包含外部联系方式或网址").model_copy(
                update={"claim_terms": external_contact_claims(full_text)}
            )
        )
    performance = tuple(
        term
        for term in contains_any(full_text, PERFORMANCE_TERMS)
        if not supports_affirmative_term(resolved, term)
    )
    if performance:
        findings.append(
            _located_claim_finding(
                "UNVERIFIED_PERFORMANCE",
                "listing",
                "存在未经证实的绝对性能：" + "、".join(performance),
                "请提供本产品的说明书、材质或涂层规格、测试报告或经批准的产品技术资料",
                performance,
            )
        )
    safety = tuple(
        term
        for term in contains_any(full_text, SAFETY_TERMS)
        if not supports_affirmative_term(resolved, term)
    )
    if safety:
        findings.append(
            _located_claim_finding(
                "UNVERIFIED_SAFETY",
                "listing",
                "存在未经证实的安全宣称：" + "、".join(safety),
                "需要安全测试、认证或合规文件",
                safety,
            )
        )
    compatibility = tuple(
        term
        for term in contains_any(full_text, COMPATIBILITY_TERMS)
        if not supports_affirmative_term(resolved, term)
    )
    if compatibility:
        findings.append(
            _located_claim_finding(
                "OVERBROAD_COMPATIBILITY",
                "bullets",
                "兼容性范围过宽：" + "、".join(compatibility),
                "需要逐项兼容性实测",
                compatibility,
            )
        )
    classification = contains_any(full_text, _WATER_CLASSIFICATION_TERMS)
    has_classification = any(supports_affirmative_term(resolved, term) for term in classification)
    if classification and not has_classification:
        findings.append(
            _located_claim_finding(
                "PRODUCT_CLASSIFICATION_UNRESOLVED",
                "listing",
                "水上穿戴产品的监管分类尚未确认",
                "需要包装标签、合规分类或卖家确认",
                classification,
            )
        )
    ambiguity = _ACCESSORY_AMBIGUITY_RE.search(full_text)
    if ambiguity is not None:
        findings.append(
            _located_claim_finding(
                "ACCESSORY_COUNT_AMBIGUITY",
                "listing",
                "皮革配件与水袋共用一个数量，无法确定逐项包装内容",
                "需要包装清单、BOM或卖家逐项确认",
                (ambiguity.group(0),),
            )
        )
    localization = contains_any(full_text, _UNNATURAL_PHRASES)
    if localization:
        findings.append(
            finding(
                "LOCALIZATION_LANGUAGE",
                "WARN",
                "listing",
                "存在不自然或易误解的美式表达：" + "、".join(localization),
            )
        )
    return findings


def highlights_density_findings(request: ListingReviewRequest) -> list[ReviewFinding]:
    """Warn when item_highlights uses very little of its available budget."""
    findings: list[ReviewFinding] = []
    ih_len = plain_len(request.item_highlights)
    max_budget = request.rules.item_highlights_max
    if max_budget < 1:
        return findings
    pct_used = ih_len / max_budget
    if pct_used < _HIGHLIGHTS_DENSITY_WARN_PCT and ih_len < _HIGHLIGHTS_DENSITY_WARN_CHARS:
        findings.append(
            finding(
                "HIGHLIGHTS_DENSITY",
                "WARN",
                "item_highlights",
                f"Item Highlights仅使用{ih_len}/{max_budget}字符（{pct_used:.0%}），"
                "建议补充配件清单、尺寸或使用场景等关键信息",
            )
        )
    return findings


def search_term_findings(request: ListingReviewRequest) -> list[ReviewFinding]:
    """Check backend search terms for duplication, filler, and unverified claims."""
    findings: list[ReviewFinding] = []
    terms = request.backend_search_terms.strip()
    if not terms:
        return findings

    dup_pct = search_term_duplication_pct(
        terms,
        request.title,
        request.item_highlights,
        request.bullets,
    )
    if dup_pct > _SEARCH_TERM_DUPLICATION_WARN_PCT:
        findings.append(
            finding(
                "SEARCH_TERM_DUPLICATION",
                "WARN",
                "backend_search_terms",
                f"后台搜索词与可见字段重复率 {dup_pct:.0f}%（阈值{_SEARCH_TERM_DUPLICATION_WARN_PCT:.0f}%），"
                "建议仅保留未见字段的增量词",
            )
        )

    unverified = unverified_search_term_claims(terms)
    if unverified:
        findings.append(
            finding(
                "SEARCH_TERM_CLAIM",
                "BLOCK",
                "backend_search_terms",
                "后台搜索词包含未证实的性能表述：" + "、".join(unverified),
                "需要对应测试报告或经批准的产品资料以支持该表述",
            ).model_copy(update={"claim_terms": unverified})
        )

    return findings


__all__ = ["content_findings", "field_findings", "highlights_density_findings", "search_term_findings"]
