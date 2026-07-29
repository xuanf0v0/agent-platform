"""Pure helpers for the v2 rule-assisted conversational workflow."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Final

from amazon_create.schemas.conversation import (
    CandidateStatus,
    DialogueIntent,
    DiscussionBlock,
    DiscussionStatus,
    FactCandidate,
)
from amazon_create.schemas.workflow import CreationStage, StageArtifact

_CONFIRM_WORDS: Final[frozenset[str]] = frozenset(
    {"确认", "认可", "通过", "没问题", "正确", "可以", "ok", "yes", "approve", "confirmed"}
)
_CONTINUE_WORDS: Final[frozenset[str]] = frozenset(
    {"继续", "下一步", "next", "continue", "往下"}
)
_REJECT_WORDS: Final[frozenset[str]] = frozenset(
    {"不认可", "不正确", "有问题", "重做", "reject", "no"}
)

_STAGE_BLOCKS: Final[dict[CreationStage, tuple[tuple[str, tuple[str, ...]], ...]]] = {
    CreationStage.AUDIENCE: (
        ("类目市场概况", ("category_market_overview",)),
        ("目标受众画像", ("audience_profiles",)),
        ("购买动机与消费者关注", ("purchase_motivations", "shopper_concerns")),
        ("好评、差评与市场结论", ("positive_reviews", "negative_reviews", "market_conclusion", "data_notes")),
    ),
    CreationStage.PRODUCT: (
        ("产品参数与消费者价值", ("parameter_analysis",)),
        ("资料一致性与待确认项", ("consistency_checks", "product_conclusion")),
    ),
    CreationStage.COMPETITOR: (
        ("竞品选择与基础对比", ("selection_basis", "basic_comparison")),
        ("功能参数与标题策略", ("feature_comparison", "title_analysis")),
        ("五点、评论一致性与结论", ("bullet_analysis", "promise_review_consistency", "competitor_conclusion")),
    ),
    CreationStage.SELLING_POINTS: (
        ("五个核心卖点", ("selling_points",)),
    ),
    CreationStage.KEYWORDS: (
        ("关键词分类与TOP20词根", ("keyword_categories", "top20_roots")),
        ("TOP20关键词与字段分配", ("top20_keywords", "keyword_allocation")),
    ),
    CreationStage.FINAL_COPY: (
        ("三套标题与推荐版本", ("title_variants", "recommended_variant")),
        ("五点与产品描述", ("bullets", "product_description")),
        ("后台词、Rufus与风险", ("search_terms", "shopping_questions", "compliance_risks", "return_risks")),
        ("创作逻辑与完整上传稿", ("creation_logic_zh", "final_report")),
    ),
    CreationStage.IMAGE_HANDOFF: (("图片流程选择", ("prompt_zh",)),),
    CreationStage.IMAGE_ANALYSIS: (("图片组分析", ()),),
    CreationStage.IMAGE_PLAN: (("主图与七张辅图方案", ()),),
}


def classify_intent(text: str) -> DialogueIntent:
    """Classify common control intents without letting them mutate facts implicitly."""
    clean = " ".join(text.strip().casefold().split())
    if any(token in clean for token in _REJECT_WORDS):
        return DialogueIntent.REJECT
    if clean in _CONFIRM_WORDS or any(clean.startswith(token) for token in ("确认以上", "认可以上")):
        return DialogueIntent.CONFIRM
    if clean in _CONTINUE_WORDS:
        return DialogueIntent.CONTINUE
    if any(token in clean for token in ("修改", "更正", "不是", "改成", "应为", "纠正")):
        return DialogueIntent.REVISE
    if clean.endswith(("?", "？")) or clean.startswith(("为什么", "怎么", "是否", "能否", "什么")):
        return DialogueIntent.QUESTION
    return DialogueIntent.PROVIDE_SOURCE


def confirm_summary_candidates(candidates: list[FactCandidate]) -> list[FactCandidate]:
    """Confirm every sourced value in one atomic summary approval."""
    confirmed: list[FactCandidate] = []
    for item in candidates:
        if not item.value.strip():
            confirmed.append(item)
            continue
        updated = item.model_copy(update={"status": CandidateStatus.CONFIRMED})
        updated = updated.model_copy(
            update={
                "confirmed_revision": updated.revision,
                "confirmed_digest": updated.value_digest,
                "conflict_values": (),
            }
        )
        confirmed.append(updated)
    return confirmed


def fact_summary_markdown(candidates: list[FactCandidate]) -> str:
    """Render the complete extracted-fact summary for one chat confirmation."""
    groups: dict[str, list[FactCandidate]] = defaultdict(list)
    for item in candidates:
        if item.value.strip():
            groups[item.group].append(item)
    if not groups:
        return "尚未从资料中提取到明确产品事实。请继续补充产品 ASIN、站点和产品资料。"
    lines = ["## 产品事实摘要", "以下内容仅来自你提供的原文或明确的公开 ASIN 快照："]
    for group, rows in groups.items():
        lines.append(f"\n### {group}")
        lines.extend(f"- **{item.label_zh}**：{item.value}" for item in rows)
    unresolved = [item for item in candidates if item.required and not item.value.strip()]
    if unresolved:
        lines.append("\n### 尚缺信息")
        lines.extend(f"- {item.label_zh}：{item.question_zh}" for item in unresolved[:20])
    lines.append("\n请直接回复“确认”，或在一条消息中列出需要修改、补充的字段。")
    return "\n".join(lines)


def blocks_for_artifact(artifact: StageArtifact) -> list[DiscussionBlock]:
    """Create deterministic blocks for one generated stage artifact."""
    definitions = _STAGE_BLOCKS.get(artifact.stage, (("阶段结果", tuple(artifact.payload)),))
    return [
        DiscussionBlock(
            block_id=f"{artifact.stage.value}:{index}",
            stage=artifact.stage.value,
            title_zh=title,
            payload_keys=keys,
            status=DiscussionStatus.ACTIVE if index == 1 else DiscussionStatus.PENDING,
        )
        for index, (title, keys) in enumerate(definitions, start=1)
    ]


def block_markdown(block: DiscussionBlock, artifact: StageArtifact) -> str:
    """Render only the payload slice associated with one discussion block."""
    lines = [f"## {block.title_zh}"]
    if artifact.summary_zh and block.block_id.endswith(":1"):
        lines.append(artifact.summary_zh)
    keys = block.payload_keys or tuple(artifact.payload)
    for key in keys:
        if key not in artifact.payload:
            continue
        lines.append(f"\n### {_humanize_key(key)}")
        lines.append(_render_value(artifact.payload[key]))
    if artifact.evidence_notes_zh:
        lines.append(f"\n> 规则与证据：{artifact.evidence_notes_zh}")
    lines.append("\n请回复“确认”进入下一讨论块，或直接提出修改意见。")
    return "\n".join(lines)


def rule_hits_for_state(
    *,
    candidates: list[FactCandidate],
    stage: CreationStage,
    research_status: str,
    downstream_stale: bool,
) -> list[str]:
    """Build concise always-visible rule status for the sidebar."""
    hits = ["所有产品事实以用户资料为准", "竞品与第三方研究不能授权我方规格", f"阶段顺序门：{stage.value}"]
    if any(item.status == CandidateStatus.CONFLICT for item in candidates):
        hits.append("存在冲突事实：禁止自动覆盖")
    if any(item.required and not item.value.strip() for item in candidates):
        hits.append("存在缺失必需事实：后续宣称受限")
    if research_status:
        hits.append(f"ASIN 研究状态：{research_status}")
    if downstream_stale:
        hits.append("事实已变更：相关阶段结果已失效")
    return hits


def dependency_start_for_fact(key: str) -> CreationStage:
    """Return earliest stage invalidated by a changed confirmed fact."""
    if key in {"marketplace", "language", "product_type", "product_asin"}:
        return CreationStage.AUDIENCE
    if key in {"brand", "media_category", "listing_scope"}:
        return CreationStage.PRODUCT
    if key == "competitor_asins":
        return CreationStage.COMPETITOR
    return CreationStage.PRODUCT


def _humanize_key(key: str) -> str:
    mapping = {
        "category_market_overview": "类目市场概况",
        "audience_profiles": "目标受众画像",
        "purchase_motivations": "购买动机",
        "shopper_concerns": "消费者关注问题",
        "positive_reviews": "好评分析",
        "negative_reviews": "差评分析",
        "market_conclusion": "市场调研结论",
        "data_notes": "数据说明",
        "parameter_analysis": "产品参数解读",
        "consistency_checks": "资料一致性检查",
        "product_conclusion": "产品分析结论",
        "selling_points": "五个核心卖点",
        "top20_roots": "TOP20词根",
        "top20_keywords": "TOP20关键词",
        "keyword_allocation": "关键词分配",
        "final_report": "完整报告",
    }
    return mapping.get(key, key.replace("_", " ").title())


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "暂无可验证数据"
        if all(isinstance(item, dict) for item in value):
            headers = list(dict.fromkeys(key for item in value for key in item))[:8]
            lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
            for item in value[:20]:
                cells = [str(item.get(key, "")).replace("\n", " ").replace("|", "/") for key in headers]
                lines.append("| " + " | ".join(cells) + " |")
            return "\n".join(lines)
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return "\n".join(f"- **{key}**：{item}" for key, item in value.items())
    return str(value)


__all__ = [
    "block_markdown",
    "blocks_for_artifact",
    "classify_intent",
    "confirm_summary_candidates",
    "dependency_start_for_fact",
    "fact_summary_markdown",
    "rule_hits_for_state",
]
