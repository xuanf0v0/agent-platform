"""Deterministic, explainable product opportunity scoring."""

from __future__ import annotations

from .models import Candidate, Decision, ResearchConstraints, ScoreBreakdown


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 2)


def _inverse(value: float | None, ceiling: float) -> float:
    if value is None:
        return 50.0
    return _clamp(100 - value / max(ceiling, 1) * 100)


def score_candidate(candidate: Candidate, constraints: ResearchConstraints) -> Candidate:
    demand = (
        _clamp((candidate.monthly_search_volume or 0) / 100000 * 100)
        if candidate.monthly_search_volume is not None
        else 45
    )
    competition = _inverse(candidate.review_count, 5000)
    if candidate.top3_share_pct is not None:
        competition = _clamp((competition * 0.6) + ((100 - candidate.top3_share_pct) * 0.4))
    profitability = 45.0
    margin = None
    if (
        candidate.price_usd is not None
        and candidate.cost_usd is not None
        and candidate.price_usd > 0
    ):
        fees = candidate.price_usd * 0.35
        margin = (candidate.price_usd - candidate.cost_usd - fees) / candidate.price_usd * 100
        candidate.estimated_margin_pct = round(margin, 2)
        profitability = _clamp(margin / max(constraints.target_margin_pct, 1) * 100)
    trend = _clamp(50 + (candidate.trend_pct or 0) * 2)
    differentiation = _clamp(70 - (candidate.review_count or 0) / 1000 * 30)
    supply = _clamp(40 + min(candidate.supplier_count or 0, 20) * 3)
    risk = _clamp(100 - len(candidate.risk_flags) * 25)
    overall = _clamp(
        demand * 0.20
        + competition * 0.20
        + profitability * 0.25
        + trend * 0.10
        + differentiation * 0.10
        + supply * 0.10
        + risk * 0.05
    )
    rationale = {
        "demand": "搜索量越高，需求分越高；缺少搜索量时按证据缺口处理。",
        "competition": "评论量和头部集中度越低，竞争分越高。",
        "profitability": "按售价、采购成本和 35% 综合平台/投放/退货成本估算。",
        "trend": "趋势增长率转换为 0–100 分；缺少趋势时使用中性分。",
        "differentiation": "竞品评论规模较小且市场分散时，差异化空间更高。",
        "supply": "供应商数量和采购信息越完整，可执行性越高。",
        "risk": "每个未解决风险标记扣减 25 分。",
    }
    candidate.score = ScoreBreakdown(
        demand=demand,
        competition=competition,
        profitability=profitability,
        trend=trend,
        differentiation=differentiation,
        supply=supply,
        risk=risk,
        overall=overall,
        rationale=rationale,
    )
    return candidate


def decide(
    candidates: list[Candidate], constraints: ResearchConstraints, gaps: list[str]
) -> Decision | None:
    if not candidates:
        return None
    best = max(candidates, key=lambda item: item.score.overall if item.score else 0)
    score = best.score.overall if best.score else 0
    hard_fail = bool(
        best.estimated_margin_pct is not None
        and best.estimated_margin_pct < constraints.min_margin_pct
    )
    missing_economics = best.price_usd is None or best.cost_usd is None
    if hard_fail or score < 60:
        return Decision.NO_GO
    if score >= 75 and not missing_economics and not gaps:
        return Decision.GO
    return Decision.CONDITIONAL_GO
