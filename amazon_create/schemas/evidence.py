"""Evidence tiers and fact-ledger authorization for staged creation."""

from __future__ import annotations

import re
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict


class EvidenceTier(IntEnum):
    """Higher number = stronger authority. Lower tiers cannot override higher facts."""

    HYPOTHESIS = 1
    COMPETITOR_PUBLIC = 2  # competitor PDP, reviews, Q&A
    THIRD_PARTY_MCP = 3  # SellerSprite / SIF / Sorftime
    BRAND_FIRST_PARTY = 4  # Brand Analytics, SQP, seller experiments
    PRODUCT_CONFIRMED = 5  # user brief, manual, packaging, certificates
    LEGAL_SAFETY = 6
    AMAZON_OFFICIAL = 7  # Seller Central, category validators, Amazon announcements


class EvidenceSourceKind(StrEnum):
    """Machine-readable source family for ledger rows."""

    AMAZON_OFFICIAL = "amazon_official"
    LEGAL_SAFETY = "legal_safety"
    PRODUCT_CONFIRMED = "product_confirmed"
    BRAND_FIRST_PARTY = "brand_first_party"
    THIRD_PARTY_MCP = "third_party_mcp"
    COMPETITOR_PUBLIC = "competitor_public"
    HYPOTHESIS = "hypothesis"


_KIND_TO_TIER: dict[EvidenceSourceKind, EvidenceTier] = {
    EvidenceSourceKind.AMAZON_OFFICIAL: EvidenceTier.AMAZON_OFFICIAL,
    EvidenceSourceKind.LEGAL_SAFETY: EvidenceTier.LEGAL_SAFETY,
    EvidenceSourceKind.PRODUCT_CONFIRMED: EvidenceTier.PRODUCT_CONFIRMED,
    EvidenceSourceKind.BRAND_FIRST_PARTY: EvidenceTier.BRAND_FIRST_PARTY,
    EvidenceSourceKind.THIRD_PARTY_MCP: EvidenceTier.THIRD_PARTY_MCP,
    EvidenceSourceKind.COMPETITOR_PUBLIC: EvidenceTier.COMPETITOR_PUBLIC,
    EvidenceSourceKind.HYPOTHESIS: EvidenceTier.HYPOTHESIS,
}


def tier_for_kind(kind: EvidenceSourceKind | str) -> EvidenceTier:
    """Map source kind to numeric tier."""
    if isinstance(kind, EvidenceSourceKind):
        return _KIND_TO_TIER[kind]
    try:
        return _KIND_TO_TIER[EvidenceSourceKind(kind)]
    except ValueError:
        return EvidenceTier.HYPOTHESIS


class FactStatus(StrEnum):
    VERIFIED = "verified"
    MISSING = "missing"
    CONFLICT = "conflict"
    HYPOTHESIS = "hypothesis"


# Claims that require PRODUCT_CONFIRMED or higher before final copy.
HARD_CLAIM_KEYS: frozenset[str] = frozenset(
    {
        "dimension",
        "dimensions",
        "size",
        "mesh",
        "gauge",
        "weight",
        "capacity",
        "count",
        "quantity",
        "material",
        "finish",
        "certification",
        "certificate",
        "voltage",
        "compatibility",
        "warranty",
        "performance",
        "origin",
        "made_in",
        "test_result",
        "load_rating",
    }
)

# Patterns that must not appear as invented absolutes without high-tier evidence.
UNSUPPORTED_ABSOLUTE_PATTERNS: tuple[str, ...] = (
    "100%",
    "guaranteed",
    "rust proof",
    "rustproof",
    "waterproof forever",
    "indestructible",
    "predator proof",
    "best seller",
    "number one",
    "#1",
)


class FactRow(BaseModel):
    """One claim in the evidence ledger with tiered provenance."""

    model_config = ConfigDict(frozen=True)

    fact: str
    value: str = ""
    source_kind: EvidenceSourceKind = EvidenceSourceKind.PRODUCT_CONFIRMED
    source_label: str = "user"
    scope: str = "parent"
    status: FactStatus = FactStatus.MISSING
    note: str = ""

    @property
    def tier(self) -> EvidenceTier:
        return tier_for_kind(self.source_kind)

    @property
    def authorizes_hard_claim(self) -> bool:
        """True when this row can back dimensions/certs/performance in final copy."""
        return (
            self.status == FactStatus.VERIFIED
            and self.tier >= EvidenceTier.PRODUCT_CONFIRMED
            and bool(self.value.strip())
            and self.value.strip() not in {"待补", "未验证", "N/A", "-"}
        )


class EvidencePolicy(BaseModel):
    """Static precedence text for prompts and UI."""

    model_config = ConfigDict(frozen=True)

    order_zh: tuple[str, ...] = (
        "1. Amazon 官方规则（Seller Central / 类目校验 / 公告）",
        "2. 法律和安全要求",
        "3. 已确认产品资料（brief / 说明书 / 包装 / 证书）",
        "4. 品牌后台数据（SQP / Brand Analytics 等）",
        "5. SellerSprite 等第三方数据（仅市场上下文）",
        "6. 竞品页面、评论、Q&A（仅结构/语言参考）",
        "7. 定性假设（必须标注 hypothesis，不得写成事实）",
    )
    rules_zh: tuple[str, ...] = (
        "低等级信息不能覆盖高等级事实。",
        "第三方与竞品数据不能单独背书本产品规格、认证或功效。",
        "没有来源的数字、认证和性能声明不得进入最终稿；缺失写「待补」。",
        "百分比仅在有可引用数据集与分母时输出，否则定性 + hypothesis。",
    )


EVIDENCE_POLICY = EvidencePolicy()


class ClaimAuthorizationResult(BaseModel):
    """Outcome of scanning final copy against the fact ledger."""

    model_config = ConfigDict(frozen=True)

    allowed: bool = True
    blocked_claims: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


def merge_fact_rows(
    existing: tuple[FactRow, ...] | list[FactRow],
    incoming: FactRow,
) -> tuple[FactRow, ...]:
    """Insert or replace by fact key; higher tier / verified wins on conflict."""
    rows = {row.fact.casefold(): row for row in existing}
    key = incoming.fact.casefold()
    prior = rows.get(key)
    if prior is None:
        rows[key] = incoming
        return tuple(rows.values())
    if incoming.tier > prior.tier:
        rows[key] = incoming
    elif incoming.tier == prior.tier:
        if incoming.status == FactStatus.VERIFIED and prior.status != FactStatus.VERIFIED:
            rows[key] = incoming
        elif (
            incoming.status == FactStatus.VERIFIED
            and prior.status == FactStatus.VERIFIED
            and incoming.value.strip()
            and prior.value.strip()
            and incoming.value.strip().casefold() != prior.value.strip().casefold()
        ):
            rows[key] = incoming.model_copy(
                update={
                    "status": FactStatus.CONFLICT,
                    "note": f"conflict with prior value {prior.value!r}",
                }
            )
        else:
            rows[key] = incoming
    # lower tier cannot override higher
    return tuple(rows.values())


def authorize_copy_claims(
    *,
    title: str,
    item_highlights: str,
    bullets: list[str],
    ledger: tuple[FactRow, ...] | list[FactRow],
) -> ClaimAuthorizationResult:
    """Block unsourced hard claims and absolute hype in final copy text."""
    full = " ".join([title, item_highlights, *bullets]).casefold()
    verified_hard = {
        row.fact.casefold(): row
        for row in ledger
        if row.authorizes_hard_claim
        and any(token in row.fact.casefold() for token in HARD_CLAIM_KEYS)
    }
    blocked: list[str] = []
    warnings: list[str] = []
    unresolved: list[str] = []

    for row in ledger:
        if row.status in {FactStatus.MISSING, FactStatus.HYPOTHESIS}:
            if any(token in row.fact.casefold() for token in HARD_CLAIM_KEYS):
                unresolved.append(f"{row.fact}:待补")

    for phrase in UNSUPPORTED_ABSOLUTE_PATTERNS:
        if phrase in full:
            # absolutes need product-confirmed+ evidence explicitly allowing them
            if not any(
                row.authorizes_hard_claim and phrase in row.value.casefold()
                for row in ledger
            ):
                blocked.append(f"unsupported_absolute:{phrase}")

    # Competitor-only or MCP-only rows never authorize hard product claims
    for row in ledger:
        if row.tier < EvidenceTier.PRODUCT_CONFIRMED and row.status == FactStatus.VERIFIED:
            if any(token in row.fact.casefold() for token in HARD_CLAIM_KEYS):
                warnings.append(
                    f"low_tier_cannot_authorize:{row.fact}({row.source_kind.value})"
                )

    # If copy mentions certification-like tokens without ledger auth
    cert_tokens = ("certified", "certification", "ul listed", "fda", "ce marked", "iso ")
    if any(tok in full for tok in cert_tokens) and not any(
        "cert" in k for k in verified_hard
    ):
        blocked.append("certification_claim_without_product_evidence")

    # Numeric density: many digits in title without any verified dimension/count
    digit_spans = re.findall(r"\d+(?:[./]\d+)?", title)
    has_size_auth = any(
        row.authorizes_hard_claim
        and any(t in row.fact.casefold() for t in ("size", "dimension", "mesh", "gauge", "count"))
        for row in ledger
    )
    if len(digit_spans) >= 2 and not has_size_auth and not any(
        row.authorizes_hard_claim for row in ledger if "spec" in row.fact.casefold()
    ):
        # soft: warn rather than block if only one vague number; block multi-spec invention
        warnings.append("numeric_specs_in_title_without_verified_ledger")

    allowed = not blocked
    return ClaimAuthorizationResult(
        allowed=allowed,
        blocked_claims=tuple(blocked),
        warnings=tuple(warnings[:20]),
        unresolved=tuple(dict.fromkeys(unresolved)),
    )


def research_as_ledger_rows(research: dict) -> tuple[FactRow, ...]:
    """Convert MCP research brief into low-tier market-context ledger rows only."""
    rows: list[FactRow] = []
    keywords = research.get("allowed_keywords") or []
    if isinstance(keywords, list):
        for i, kw in enumerate(keywords[:16]):
            rows.append(
                FactRow(
                    fact=f"market_keyword_{i}",
                    value=str(kw),
                    source_kind=EvidenceSourceKind.THIRD_PARTY_MCP,
                    source_label=str(research.get("mode") or "mcp"),
                    status=FactStatus.VERIFIED,
                    note="market context only; not product fact",
                )
            )
    for gap in research.get("gaps") or []:
        rows.append(
            FactRow(
                fact=f"research_gap:{gap}",
                value="",
                source_kind=EvidenceSourceKind.THIRD_PARTY_MCP,
                source_label="mcp",
                status=FactStatus.MISSING,
            )
        )
    return tuple(rows)


def evidence_prompt_block() -> str:
    """Short system/user prompt appendix for evidence discipline."""
    lines = ["EVIDENCE HIERARCHY (high wins):"]
    lines.extend(EVIDENCE_POLICY.order_zh)
    lines.append("RULES:")
    lines.extend(EVIDENCE_POLICY.rules_zh)
    return "\n".join(lines)
