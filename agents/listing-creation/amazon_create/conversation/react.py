"""Bounded ReAct planner and MCP research executor for the chat workflow."""

from __future__ import annotations

import json
from typing import Any, Final

from amazon_create.config import Settings
from amazon_create.llm import get_llm
from amazon_create.research_bridge import load_asin_research_context, load_research_context
from amazon_create.schemas.brief import ProductBrief
from amazon_create.schemas.conversation import (
    FactCandidate,
    ReActAction,
    ReActObservation,
    ReActTool,
    ReActTurn,
)
from amazon_create.schemas.workflow import CreationStage
from amazon_create.utils.json_extract import JsonExtractError, extract_json_object

_MAX_ACTIONS: Final[int] = 2
_RESEARCH_STAGES: Final[frozenset[CreationStage]] = frozenset(
    {CreationStage.AUDIENCE, CreationStage.PRODUCT, CreationStage.COMPETITOR, CreationStage.KEYWORDS}
)


def run_react_turn(
    *,
    stage: CreationStage,
    trigger: str,
    brief: ProductBrief,
    confirmed_facts: list[FactCandidate],
    settings: Settings,
) -> tuple[dict[str, Any], ReActTurn]:
    """Plan approved tools, execute them once, and return a bounded research context."""
    actions = _validated_actions(
        _model_actions(stage, trigger, brief, confirmed_facts, settings),
        stage=stage,
        brief=brief,
    )
    research, observations = _execute_actions(actions, brief=brief, settings=settings)
    return research, ReActTurn(
        stage=stage.value,
        trigger=trigger[:160],
        actions=tuple(actions),
        observations=tuple(observations),
    )


def _model_actions(
    stage: CreationStage,
    trigger: str,
    brief: ProductBrief,
    confirmed_facts: list[FactCandidate],
    settings: Settings,
) -> list[ReActAction]:
    facts = {item.key: item.value for item in confirmed_facts if item.value.strip()}
    try:
        response = get_llm(settings, role="review").complete(
            (
                "REACT_PLANNER_V1. You are a bounded Amazon listing research planner. "
                "Do not reveal chain-of-thought and do not write listing copy. Return JSON only: "
                '{"actions":[{"tool":"market_research|asin_research|continue"}]}. '
                "Choose only necessary whitelist tools for the current workflow stage. "
                "Product facts must never be inferred from tool results."
            ),
            json.dumps(
                {
                    "stage": stage.value,
                    "trigger": trigger[:500],
                    "confirmed_facts": facts,
                    "available_tools": [item.value for item in ReActTool],
                },
                ensure_ascii=False,
            ),
            json_mode=True,
            temperature=0,
        )
        payload = extract_json_object(response)
    except (JsonExtractError, RuntimeError, ValueError, TypeError):
        return []
    raw_actions = payload.get("actions") if isinstance(payload, dict) else []
    if not isinstance(raw_actions, list):
        return []
    actions: list[ReActAction] = []
    for item in raw_actions[:_MAX_ACTIONS]:
        if not isinstance(item, dict):
            continue
        try:
            tool = ReActTool(str(item.get("tool") or ""))
        except ValueError:
            continue
        actions.append(ReActAction(tool=tool, label_zh=_tool_label(tool)))
    return actions


def _validated_actions(
    model_actions: list[ReActAction],
    *,
    stage: CreationStage,
    brief: ProductBrief,
) -> list[ReActAction]:
    """Apply workflow policy; the model cannot call unapproved tools or loop."""
    required = _required_tools(stage, brief)
    selected = [action.tool for action in model_actions if action.tool != ReActTool.CONTINUE]
    tools = list(dict.fromkeys([*required, *selected]))[:_MAX_ACTIONS]
    if not tools:
        tools = [ReActTool.CONTINUE]
    return [ReActAction(tool=tool, label_zh=_tool_label(tool)) for tool in tools]


def _required_tools(stage: CreationStage, brief: ProductBrief) -> list[ReActTool]:
    if stage not in _RESEARCH_STAGES:
        return []
    tools: list[ReActTool] = []
    if stage in {CreationStage.AUDIENCE, CreationStage.COMPETITOR, CreationStage.KEYWORDS}:
        tools.append(ReActTool.MARKET_RESEARCH)
    if stage in {CreationStage.AUDIENCE, CreationStage.PRODUCT, CreationStage.COMPETITOR} and (
        brief.product_asin or brief.competitors
    ):
        tools.append(ReActTool.ASIN_RESEARCH)
    return tools


def _execute_actions(
    actions: list[ReActAction],
    *,
    brief: ProductBrief,
    settings: Settings,
) -> tuple[dict[str, Any], list[ReActObservation]]:
    research = _empty_research_context(brief.marketplace)
    observations: list[ReActObservation] = []
    for action in actions:
        if action.tool == ReActTool.CONTINUE:
            observations.append(
                ReActObservation(
                    tool=action.tool,
                    status="skipped",
                    summary_zh="当前阶段仅使用已确认事实和已批准阶段结论。",
                )
            )
            continue
        if action.tool == ReActTool.MARKET_RESEARCH:
            result = load_research_context(
                settings,
                product_name=brief.product_name,
                marketplace=brief.marketplace,
                specs=brief.specs_text,
            )
            _merge_research_context(research, result)
            observations.append(_observation(action.tool, result))
            continue
        if action.tool == ReActTool.ASIN_RESEARCH:
            targets = [
                (brief.product_asin, "product"),
                *((asin, "competitor") for asin in brief.competitors[:3]),
            ]
            if not targets or not brief.marketplace:
                observations.append(
                    ReActObservation(
                        tool=action.tool,
                        status="unavailable",
                        summary_zh="缺少已确认的 ASIN 或目标站点，未调用 ASIN 研究。",
                    )
                )
                continue
            statuses: list[str] = []
            for asin, relationship in targets:
                if not asin:
                    continue
                result = load_asin_research_context(
                    settings,
                    asin=asin,
                    marketplace=brief.marketplace,
                )
                statuses.append(str(result.get("mode") or "unavailable"))
                research["asin_research"].append(
                    {"asin": asin, "relationship": relationship, "research": result}
                )
            status = "complete" if any(value == "live" for value in statuses) else "degraded"
            if statuses and all(value == "unavailable" for value in statuses):
                status = "unavailable"
            observations.append(
                ReActObservation(
                    tool=action.tool,
                    status=status,
                    summary_zh=f"已查询 {len(statuses)} 个 ASIN 公开快照；结果状态：{', '.join(statuses) or '无'}。",
                )
            )
    return research, observations


def _empty_research_context(marketplace: str) -> dict[str, Any]:
    return {
        "mode": "unavailable",
        "marketplace": marketplace,
        "allowed_keywords": [],
        "market_metrics": [],
        "cited_evidence": [],
        "asin_research": [],
        "category_research": {},
        "gaps": [],
        "guidance": "No ReAct research action was required for this stage.",
    }


def _merge_research_context(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("allowed_keywords", "market_metrics", "cited_evidence", "gaps"):
        value = source.get(key)
        if isinstance(value, list):
            target[key] = [*target[key], *value]
    for key in ("category_research", "guidance", "mode", "query"):
        if source.get(key):
            target[key] = source[key]
    asin_research = source.get("asin_research")
    if isinstance(asin_research, list):
        target["asin_research"].extend(asin_research)


def _observation(tool: ReActTool, result: dict[str, Any]) -> ReActObservation:
    mode = str(result.get("mode") or "unavailable")
    status = "complete" if mode == "live" else "degraded"
    if mode == "unavailable":
        status = "unavailable"
    return ReActObservation(
        tool=tool,
        status=status,
        summary_zh=(
            f"市场研究状态：{mode}；关键词 {len(result.get('allowed_keywords') or [])} 条，"
            f"市场指标 {len(result.get('market_metrics') or [])} 条。"
        ),
    )


def _tool_label(tool: ReActTool) -> str:
    return {
        ReActTool.MARKET_RESEARCH: "市场与关键词研究",
        ReActTool.ASIN_RESEARCH: "ASIN 公开快照研究",
        ReActTool.CONTINUE: "继续当前阶段",
    }[tool]


__all__ = ["run_react_turn"]
