"""Deterministic copy-side funnel hypotheses (never measured root cause)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.automatic_models import FunnelHypothesis

if TYPE_CHECKING:
    from amazon_copy.review.diagnosis_models import ListingDiagnosisReport
    from amazon_copy.review.models import ListingReviewReport

_MAX_HYPOTHESES = 4
_SHORT_TITLE_CHARS = 40

_FACT_CODES = frozenset(
    {
        "UNAUTHORIZED_NEW_FACT",
        "MISSING_REQUIRED_FACT",
        "UNRESOLVED_CORE_FACT",
        "FACT_CONFLICT",
        "CLAIM_NEEDS_EVIDENCE",
    }
)
_FORMAT_CODES = frozenset(
    {
        "TITLE_TOO_LONG",
        "TITLE_TOO_SHORT",
        "HIGHLIGHTS_TOO_LONG",
        "BULLET_COUNT",
        "BACKEND_SEARCH_TERMS_BYTES",
    }
)


def build_funnel_hypotheses(
    source_review: ListingReviewReport,
    diagnosis: ListingDiagnosisReport | None,
    *,
    title: str = "",
) -> tuple[FunnelHypothesis, ...]:
    """Map review/diagnosis signals to ordered funnel assumptions.

    Without first-party CTR/CVR data, confidence is at most ``medium`` and every
    row carries the standard non-root-cause disclaimer.
    """
    hypotheses: list[FunnelHypothesis] = []
    seen_stages: set[str] = set()

    def _add(hypothesis: FunnelHypothesis) -> None:
        if hypothesis.stage in seen_stages or len(hypotheses) >= _MAX_HYPOTHESES:
            return
        seen_stages.add(hypothesis.stage)
        hypotheses.append(hypothesis)

    title_text = title.strip()
    if title_text and len(title_text) < _SHORT_TITLE_CHARS:
        _add(
            FunnelHypothesis(
                stage="ctr",
                confidence="medium",
                basis="copy_only",
                note_zh=(
                    f"标题仅 {len(title_text)} 字符，前段身份与差异点可能偏弱，"
                    "点击率（CTR）或受主图旁标题展示影响（假设）。"
                ),
            )
        )

    finding_codes = {finding.code for finding in source_review.findings}
    fact_findings = [
        finding
        for finding in source_review.findings
        if finding.code in _FACT_CODES
        or finding.severity in {"BLOCK", "WARN"}
        and finding.field in {"title", "bullets", "item_highlights"}
        and (
            "规格" in finding.message_zh
            or "事实" in finding.message_zh
            or "证据" in finding.message_zh
            or finding.fact_key
        )
    ]
    if fact_findings or finding_codes & _FACT_CODES:
        _add(
            FunnelHypothesis(
                stage="cvr",
                confidence="medium",
                basis="review_finding",
                note_zh=(
                    "源稿存在待确认规格/事实缺口或未授权宣称，"
                    "点击后转化（CVR）可能受信任与预期管理影响（假设）。"
                ),
            )
        )

    backend = diagnosis.backend if diagnosis is not None else None
    keyword_gap = False
    if backend is not None and (
        backend.uncovered_candidates
        or backend.duplication_pct >= 40.0
        or (backend.max_bytes > 0 and backend.bytes_used < backend.max_bytes * 0.35)
    ):
        keyword_gap = True
    for coverage in source_review.keyword_coverage:
        if coverage.missing:
            keyword_gap = True
            break
    if keyword_gap:
        _add(
            FunnelHypothesis(
                stage="exposure",
                confidence="low",
                basis="keyword_context",
                note_zh=(
                    "可见字段或后台词覆盖存在缺口/高重复，"
                    "自然曝光与索引相关性可能受限（假设，非搜索量验证）。"
                ),
            )
        )

    if diagnosis is not None:
        p0 = [issue for issue in diagnosis.issues if issue.level == "P0"]
        low_scores = [
            score
            for score in diagnosis.scores
            if score.dimension in {"purchase_motivation", "selling_points"} and score.score <= 5.5
        ]
        if p0 or low_scores:
            _add(
                FunnelHypothesis(
                    stage="cart_to_purchase",
                    confidence="low",
                    basis="copy_only",
                    note_zh=(
                        "诊断显示高优先级文案问题或卖点/购买推动力偏弱，"
                        "加购到成交的最后一环可能受文案预期管理影响（假设）。"
                    ),
                )
            )

    # Prefer not inventing empty noise when format-only issues dominate with no signals.
    if not hypotheses and finding_codes & _FORMAT_CODES:
        _add(
            FunnelHypothesis(
                stage="ctr",
                confidence="low",
                basis="copy_only",
                note_zh="字段格式告警可能影响前台展示完整度，间接影响点击（假设）。",
            )
        )

    return tuple(hypotheses)


__all__ = ["build_funnel_hypotheses"]
