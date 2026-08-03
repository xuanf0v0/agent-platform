"""Minimal LangGraph chat: persistence plus one prompt-driven LLM turn."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from amazon_create.config import Settings
from amazon_create.conversation.intake_parsing import (
    extract_labeled_product_asin,
    extract_short_asin_answer,
    normalize_asin,
)
from amazon_create.conversation.visual_guidance import (
    load_visual_guidance,
    visual_guidance_requested,
)
from amazon_create.llm import get_llm
from amazon_create.research_bridge import load_asin_research_context, load_research_context
from amazon_create.schemas.conversation import (
    ConfirmedFact,
    ConversationGraphState,
    ConversationMessage,
)

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "asin_research",
            "description": "查询一个 Amazon ASIN 的公开商品快照",
            "parameters": {
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "marketplace": {"type": "string"},
                },
                "required": ["asin", "marketplace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_research",
            "description": "查询产品市场、关键词、类目和竞品研究数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "marketplace": {"type": "string"},
                    "specs": {"type": "string"},
                },
                "required": ["product_name", "marketplace"],
            },
        },
    },
]


class GraphChannels(TypedDict, total=False):
    data: dict[str, Any]
    action: dict[str, Any]


def build_conversation_graph(settings: Settings, checkpointer: Any) -> Any:
    """Compile a graph that delegates every response decision to the LLM."""

    def process(channels: GraphChannels) -> GraphChannels:
        state = ConversationGraphState.model_validate(channels["data"])
        action = dict(channels.get("action") or {})
        action_type = str(action.get("type") or "")
        state.error = ""

        if action_type == "start":
            return _result(state)
        if action_type == "enqueue_message":
            text = str(action.get("text") or "").strip()
            if text:
                state.messages.append(ConversationMessage(role="user", content=text))
                _update_asin(state, text)
                state.pending_user_message = text
            return _result(state)
        if action_type == "process_pending_message":
            if state.pending_user_message:
                _complete_turn(state, settings)
                state.pending_user_message = ""
            return _result(state)
        if action_type == "complete_streamed_message":
            reply = str(action.get("text") or "").strip()
            if reply:
                state.messages.append(ConversationMessage(role="assistant", content=reply))
            state.pending_user_message = ""
            _refresh_confirmed_facts(state, settings)
            _update_title(state)
            return _result(state)
        if action_type == "message":
            text = str(action.get("text") or "").strip()
            if text:
                state.messages.append(ConversationMessage(role="user", content=text))
                _update_asin(state, text)
                _complete_turn(state, settings)
                _refresh_confirmed_facts(state, settings)
            return _result(state)
        if action_type == "rename":
            title = str(action.get("title") or "").strip()
            if title:
                state.title = title[:80]
            return _result(state)
        if action_type == "set_asin":
            state.asin = normalize_asin(str(action.get("asin") or ""))
            return _result(state)
        return _result(state)

    builder = StateGraph(GraphChannels)
    builder.add_node("process", process)
    builder.add_edge(START, "process")
    builder.add_edge("process", END)
    return builder.compile(checkpointer=checkpointer)


def initial_graph_state(thread_id: str) -> ConversationGraphState:
    return ConversationGraphState(thread_id=thread_id, schema_version=3)


def _update_asin(state: ConversationGraphState, text: str) -> None:
    """Capture an explicitly labelled or single ASIN supplied by the user."""
    asin = extract_labeled_product_asin(text) or extract_short_asin_answer(text)
    if asin:
        state.asin = asin


def _complete_turn(state: ConversationGraphState, settings: Settings) -> None:
    user_context = _reply_context(state, settings)
    reply = get_llm(settings, role="writer").complete(
        _system_prompt(state.messages),
        user_context,
        json_mode=False,
        temperature=0.7,
    ).strip()
    if reply:
        state.messages.append(ConversationMessage(role="assistant", content=reply))
    _update_title(state)


def stream_reply(
    state: ConversationGraphState,
    settings: Settings,
) -> Iterator[str]:
    """Stream one prompt-driven reply directly from the configured model."""
    yield from get_llm(settings, role="writer").stream(
        _system_prompt(state.messages),
        _reply_context(state, settings),
        json_mode=False,
        temperature=0.7,
    )


def _reply_context(state: ConversationGraphState, settings: Settings) -> str:
    history = "\n\n".join(
        f"{message.role.upper()}: {message.content}"
        for message in state.messages[-40:]
    )
    confirmed_facts = [fact.model_dump(mode="json") for fact in state.confirmed_facts]
    asin_context = f"\n\nCURRENT_PRODUCT_ASIN: {state.asin}" if state.asin else ""
    tool_result = _run_llm_selected_tool(history, confirmed_facts, settings, asin=state.asin)
    if tool_result is None:
        return history
    return (
        history
        + asin_context
        + "\n\nCONFIRMED_PRODUCT_FACTS_FROM_PRIOR_TURNS:\n"
        + json.dumps(confirmed_facts, ensure_ascii=False)
        + "\n\nMCP_RESEARCH_RESULT (third-party candidate facts requiring user confirmation):\n"
        + json.dumps(tool_result, ensure_ascii=False)
        + "\n\nRESPONSE_REQUIREMENTS_FOR_THIS_TURN:\n"
        + "自然回应用户当前意图，并把 MCP 查询到的实质商品信息放入本轮对话供用户核对。"
        + "不得只输出 MCP 查询事实；必须结合完整会话中用户已经提供的产品资料和已确认事实，"
        + "同时指出仍缺失、冲突、含糊或需要用户确认的信息。"
        + "严格区分三类内容：用户已确认事实、MCP 待确认候选、尚待补充信息。"
        + "MCP 无有效数据时如实说明，但仍继续处理既有产品资料和合理追问。"
        + "不要使用固定模板，不要机械重复全部历史，只组织与当前决策相关的完整信息。"
    )


def _update_title(state: ConversationGraphState) -> None:
    if state.title == "新建 Listing":
        first_user = next((item.content for item in state.messages if item.role == "user"), "")
        if first_user:
            state.title = first_user.replace("\n", " ")[:36]


def _refresh_confirmed_facts(state: ConversationGraphState, settings: Settings) -> None:
    """Rebuild the UI fact snapshot without controlling the conversation flow."""
    history = "\n\n".join(
        f"{message.role.upper()}: {message.content}"
        for message in state.messages[-40:]
    )
    current = [fact.model_dump(mode="json") for fact in state.confirmed_facts]
    user = (
        "CONVERSATION:\n"
        + history
        + "\n\nCURRENT_CONFIRMED_FACTS:\n"
        + json.dumps(current, ensure_ascii=False)
    )
    try:
        raw = get_llm(settings, role="review").complete(
            _fact_extraction_prompt(),
            user,
            json_mode=True,
            temperature=0,
        )
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001 -- sidebar extraction must never break chat
        return
    rows = payload.get("facts") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return
    facts: list[ConfirmedFact] = []
    seen: set[str] = set()
    for row in rows[:128]:
        if not isinstance(row, dict):
            continue
        try:
            fact = ConfirmedFact.model_validate(row)
        except (TypeError, ValueError):
            continue
        identity = fact.key.strip().casefold()
        if not identity or not fact.label.strip() or not fact.value.strip() or identity in seen:
            continue
        seen.add(identity)
        facts.append(fact)
    state.confirmed_facts = facts


def _run_llm_selected_tool(
    history: str,
    confirmed_facts: list[dict[str, Any]],
    settings: Settings,
    *,
    asin: str = "",
) -> dict[str, Any] | None:
    """Let the model select at most one read-only MCP research operation."""
    decision_context = (
        "CONVERSATION:\n"
        + history
        + "\n\nCONFIRMED_PRODUCT_FACTS:\n"
        + json.dumps(confirmed_facts, ensure_ascii=False)
        + (f"\n\nCURRENT_PRODUCT_ASIN: {asin}" if asin else "")
    )
    try:
        selected = get_llm(settings, role="review").select_tool(
            _tool_selection_prompt(),
            decision_context,
            _TOOLS,
        )
    except Exception:  # noqa: BLE001 -- tool support is optional per provider
        return None
    if selected is None:
        return None
    tool, decision = selected
    if tool == "asin_research":
        asin = normalize_asin(str(decision.get("asin") or "")) or asin
        marketplace = str(decision.get("marketplace") or "").strip().upper()
        if asin and marketplace:
            return {
                "tool": tool,
                "result": load_asin_research_context(
                    settings,
                    asin=asin,
                    marketplace=marketplace,
                ),
            }
    if tool == "market_research":
        product_name = str(decision.get("product_name") or "").strip()
        marketplace = str(decision.get("marketplace") or "").strip().upper()
        if product_name and marketplace:
            return {
                "tool": tool,
                "result": load_research_context(
                    settings,
                    product_name=product_name,
                    marketplace=marketplace,
                    specs=str(decision.get("specs") or ""),
                ),
            }
    return None


def _system_prompt(messages: list[ConversationMessage] | None = None) -> str:
    root = Path(__file__).resolve().parents[1]
    prompt = (root / "prompts" / "agents" / "creation_agent.md").read_text(encoding="utf-8")
    workflow = (root / "resources" / "amazon-listing-creation" / "SKILL.md").read_text(encoding="utf-8")
    base = f"{prompt}\n\n{workflow}"
    if messages and visual_guidance_requested(messages):
        return f"{base}\n\n{load_visual_guidance()}"
    return base


def _fact_extraction_prompt() -> str:
    return """你只负责维护界面侧栏的已确认产品事实，不负责回复用户或推进流程。

阅读完整对话和当前事实，输出最新的完整事实集合 JSON：
{"facts":[{"key":"稳定英文键","label":"简短中文标签","value":"事实值","group":"分组","source_quote":"用户原话或确认依据"}]}

仅保留用户明确提供的产品事实，或用户在后续消息中明确确认过的助手摘要事实。每项事实必须能引用 USER 消息作为 source_quote；仅出现在 ASSISTANT 消息中的内容不得提取。用户后续纠正时覆盖旧值；用户否定、撤回或标记不确定的事实应删除。普通问题、任务指令、工作流规则、市场推测、竞品属性、MCP 数据和助手未经用户确认的推断都不是已确认事实。不要补全、猜测或生成待确认字段。ASIN、站点、品牌、产品名称、规格、材质、数量、包装、功能、兼容性、场景等只在满足上述证据条件时提取。只输出 JSON。"""


def _tool_selection_prompt() -> str:
    return """你只负责根据完整对话自主决定本轮是否调用只读研究工具，不负责回复用户。

当用户本轮提供、纠正或要求查询一个明确 Amazon ASIN，且当前消息、历史消息或已确认事实中能确定目标站点时，必须选择 asin_research。不要因为对话中还包含产品规格、说明书或其他问题而跳过 ASIN 查询。

如果只有 ASIN 而无法可靠确定站点，不要猜测站点，也不要调用参数不完整的工具。若用户明确要求市场、关键词、类目或竞品研究，且产品和站点充分，则选择 market_research。普通问答、确认、修改文案或参数不足时可以不调用工具。

工具只是补充第三方研究，不会替代完整会话中的用户产品资料。不得把竞品 ASIN 当成我方产品 ASIN；根据用户语义选择实际查询目标。"""


def _result(state: ConversationGraphState) -> GraphChannels:
    return {"data": state.model_dump(mode="json"), "action": {}}


__all__ = ["build_conversation_graph", "initial_graph_state", "stream_reply"]
