"""LangGraph workflow for rule-assisted, fully conversational listing creation."""

from __future__ import annotations

import re
from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

from amazon_create.config import Settings
from amazon_create.conversation.dialogue import (
    block_markdown,
    blocks_for_artifact,
    classify_intent,
    confirm_summary_candidates,
    dependency_start_for_fact,
    fact_summary_markdown,
    rule_hits_for_state,
)
from amazon_create.conversation.intake_parsing import (
    extract_short_asin_answer,
    extract_short_marketplace_answer,
)
from amazon_create.conversation.react import run_react_turn
from amazon_create.conversation.reasoning import (
    base_fact_candidates,
    deterministic_candidates,
    merge_candidates,
    reason_product_facts,
)
from amazon_create.pipeline.creation_pipeline import (
    apply_user_message,
    approve_stage,
    next_stage,
    run_stage,
)
from amazon_create.schemas.brief import ProductBrief
from amazon_create.schemas.conversation import (
    CandidateStatus,
    ConversationGraphState,
    ConversationMessage,
    DialogueIntent,
    DiscussionStatus,
    FactCandidate,
    SummaryStatus,
)
from amazon_create.schemas.evidence import EvidenceSourceKind, FactRow, FactStatus
from amazon_create.schemas.workflow import (
    STAGE_ORDER,
    CreationSession,
    CreationStage,
    StageArtifact,
)

_IDENTITY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "product_name",
        "marketplace",
        "language",
        "product_type",
        "brand",
        "media_category",
        "listing_scope",
        "product_asin",
    }
)
_NON_SPEC_KEYS: Final[frozenset[str]] = frozenset(
    {*_IDENTITY_KEYS, "product_asin", "competitor_asins"}
)
_SENSITIVE_TERMS: Final[frozenset[str]] = frozenset(
    {
        "儿童",
        "婴儿",
        "婴幼儿",
        "食品",
        "补剂",
        "医疗",
        "医用",
        "化妆品",
        "保健",
        "健康",
        "安全用品",
        "电子产品",
        "kids",
        "children",
        "baby",
        "infant",
        "food",
        "supplement",
        "medical",
        "cosmetic",
        "health",
        "safety",
        "electronic",
        "electrical",
    }
)
_MAX_SOURCE_BYTES: Final[int] = 128_000
_UNAVAILABLE_ANSWERS: Final[frozenset[str]] = frozenset(
    {"不知道", "不清楚", "暂无", "暂时没有", "无", "未知", "待确认", "pending", "tbd", "not sure"}
)


class GraphChannels(TypedDict, total=False):
    """Minimal channels persisted by LangGraph."""

    data: dict[str, Any]
    action: dict[str, Any]


def build_conversation_graph(settings: Settings, checkpointer: Any) -> Any:
    """Compile the v2 conversational graph with SQLite persistence."""

    def process(channels: GraphChannels) -> GraphChannels:
        state = ConversationGraphState.model_validate(channels["data"])
        action = dict(channels.get("action") or {})
        state.error = ""
        action_type = str(action.get("type") or "")

        if action_type == "start":
            _append_assistant(
                state,
                "请直接粘贴完整产品资料、说明书、ASIN、站点和已知竞品。"
                "我会先整理一份产品事实摘要供你一次确认，再以对话方式分块完成市场、"
                "产品、竞品、卖点、关键词和 Listing 创作。",
            )
        elif action_type == "message":
            _handle_message(state, str(action.get("text") or ""), settings)
        elif action_type == "revise_fact":
            _revise_fact(
                state,
                str(action.get("fact_id") or ""),
                str(action.get("value") or ""),
            )
        elif action_type == "regenerate":
            _regenerate_from_current_facts(state, settings)
        elif action_type == "rename":
            title = str(action.get("title") or "").strip()
            if title:
                state.title = title[:80]
        else:
            state.error = "unsupported_conversation_action"

        state.rule_hits = rule_hits_for_state(
            candidates=state.candidates,
            stage=state.creation_session.stage,
            research_status=state.asin_research_status,
            downstream_stale=state.downstream_stale,
        )
        return {"data": state.model_dump(mode="json"), "action": {}}

    builder = StateGraph(GraphChannels)
    builder.add_node("process", process)
    builder.add_edge(START, "process")
    builder.add_edge("process", END)
    return builder.compile(checkpointer=checkpointer)


def initial_graph_state(thread_id: str) -> ConversationGraphState:
    """Create one v2 persisted conversation."""
    return ConversationGraphState(thread_id=thread_id, schema_version=2)


def _handle_message(
    state: ConversationGraphState,
    text: str,
    settings: Settings,
) -> None:
    clean = text.strip()
    if not clean:
        state.error = "empty_message"
        return
    if state.is_legacy or state.phase == "legacy_readonly":
        state.phase = "legacy_readonly"
        _append_assistant(state, "这是旧版只读会话。请新建会话后继续使用全对话架构。")
        return

    intent = classify_intent(clean)
    state.last_intent = intent
    _append_user(state, clean)

    if state.phase in {"intake", "facts", "fact_summary"}:
        _handle_intake_turn(state, clean, intent, settings)
        return
    if state.phase == "completed":
        if intent in {DialogueIntent.PROVIDE_SOURCE, DialogueIntent.REVISE}:
            _handle_fact_revision_message(state, clean, settings)
        else:
            _append_assistant(state, "当前流程已完成。若需修改产品事实，请直接说明字段和正确值。")
        return
    _handle_workflow_turn(state, clean, intent, settings)


def _handle_intake_turn(
    state: ConversationGraphState,
    text: str,
    intent: DialogueIntent,
    settings: Settings,
) -> None:
    if state.fact_summary_status == SummaryStatus.AWAITING_CONFIRMATION and intent in {
        DialogueIntent.CONFIRM,
        DialogueIntent.CONTINUE,
    }:
        _confirm_fact_summary(state, settings)
        return

    if _handle_unavailable_intake_answer(state, text):
        return

    contextual = _contextual_intake_candidates(state, text)
    if contextual:
        if not _append_source_material(state, text):
            state.error = "source_prompt_too_large"
            _append_assistant(state, "产品资料超过 128,000 UTF-8 bytes，请分批精简后重新发送。")
            return
        state.candidates = merge_candidates(state.candidates or base_fact_candidates(), contextual)
        state.phase = "fact_summary"
        state.fact_summary_status = SummaryStatus.AWAITING_CONFIRMATION
        state.fact_summary_revision += 1
        _append_contextual_intake_reply(state, contextual)
        return

    if not _append_source_material(state, text):
        state.error = "source_prompt_too_large"
        _append_assistant(state, "产品资料超过 128,000 UTF-8 bytes，请分批精简后重新发送。")
        return
    deterministic = deterministic_candidates(text)
    candidates = merge_candidates(
        state.candidates or base_fact_candidates(),
        deterministic,
    )
    reasoned = reason_product_facts(state.source_material, candidates, settings=settings)
    state.candidates = merge_candidates(candidates, reasoned.candidates)
    state.phase = "fact_summary"
    state.fact_summary_status = SummaryStatus.AWAITING_CONFIRMATION
    state.fact_summary_revision += 1
    if reasoned.error:
        state.error = reasoned.error
    _set_next_intake_candidate(state)
    direct_updates = [item for item in deterministic if item.value.strip()]
    if _should_ack_single_field_update(text, direct_updates):
        current_values = {item.key: item for item in state.candidates}
        _append_contextual_intake_reply(
            state,
            [current_values[item.key] for item in direct_updates if item.key in current_values],
        )
        return
    _append_assistant(state, fact_summary_markdown(state.candidates))


def _confirm_fact_summary(state: ConversationGraphState, settings: Settings) -> None:
    state.candidates = confirm_summary_candidates(state.candidates)
    state.facts_revision += 1
    state.fact_summary_status = SummaryStatus.CONFIRMED
    missing_identity = [
        item
        for item in state.candidates
        if item.key in _IDENTITY_KEYS and not item.value.strip()
    ]
    if missing_identity:
        state.phase = "facts"
        state.pending_question_keys = tuple(item.key for item in missing_identity)
        _set_next_intake_candidate(state)
        questions = "\n".join(f"- {item.question_zh}" for item in missing_identity)
        missing_specs = [
            item
            for item in state.candidates
            if item.required and not item.value.strip() and item not in missing_identity
        ]
        optional_context = ""
        if missing_specs:
            optional_context = (
                "\n\n另外仍待确认的产品参数："
                + "、".join(item.label_zh for item in missing_specs[:8])
                + "。可一并补充；未提供的信息会在后续阶段标记为待确认。"
            )
        _append_assistant(
            state,
            "事实摘要已确认。开始前还缺少以下身份信息，请在一条消息中尽量补齐：\n"
            + questions
            + optional_context,
        )
        return
    if state.downstream_stale and state.restart_stage:
        _resume_invalidated_workflow(state, settings)
    else:
        _start_workflow(state, settings)


def _handle_fact_revision_message(
    state: ConversationGraphState,
    text: str,
    settings: Settings,
) -> None:
    if not _append_source_material(state, text):
        state.error = "source_prompt_too_large"
        return
    before = {item.key: item.value for item in state.confirmed_candidates()}
    explicit = deterministic_candidates(text)
    candidates = merge_candidates(state.candidates, explicit)
    reasoned = reason_product_facts(text, candidates, settings=settings)
    state.candidates = merge_candidates(candidates, reasoned.candidates)
    explicit_values = {item.key: item for item in explicit if item.value.strip()}
    state.candidates = [
        item.model_copy(
            update={
                "value": explicit_values[item.key].value,
                "status": CandidateStatus.PENDING,
                "revision": item.revision + 1,
                "confirmed_revision": 0,
                "confirmed_digest": "",
                "conflict_values": (),
                "source_label": "human_revision",
                "source_quote": explicit_values[item.key].source_quote,
            }
        )
        if item.key in explicit_values and before.get(item.key) not in {None, explicit_values[item.key].value}
        else item
        for item in state.candidates
    ]
    changed = [
        item
        for item in state.candidates
        if item.value.strip() and before.get(item.key) not in {None, item.value}
    ]
    state.fact_summary_status = SummaryStatus.AWAITING_CONFIRMATION
    state.fact_summary_revision += 1
    state.phase = "fact_summary"
    if changed:
        earliest = min(
            (dependency_start_for_fact(item.key) for item in changed),
            key=lambda stage: STAGE_ORDER.index(stage),
        )
        _invalidate_from_stage(state, earliest)
    _append_assistant(state, fact_summary_markdown(state.candidates))


def _handle_workflow_turn(
    state: ConversationGraphState,
    text: str,
    intent: DialogueIntent,
    settings: Settings,
) -> None:
    if state.creation_session.stage in {
        CreationStage.FINAL_COPY,
        CreationStage.IMAGE_HANDOFF,
        CreationStage.IMAGE_ANALYSIS,
        CreationStage.IMAGE_PLAN,
    } and any(
        token in text.casefold()
        for token in ("人工审核通过", "图片设计", "图片优化", "图片分析", "不需要图片", "跳过图片")
    ):
        state.creation_session = apply_user_message(
            state.creation_session,
            text,
            settings=settings,
        )
        if state.creation_session.stage == CreationStage.COMPLETED:
            state.phase = "completed"
            state.current_block_id = ""
            _append_assistant(state, state.creation_session.last_message_zh)
        else:
            _open_stage_blocks(state)
        return
    if intent in {DialogueIntent.CONFIRM, DialogueIntent.CONTINUE}:
        _confirm_current_block(state, settings)
        return
    if intent == DialogueIntent.QUESTION:
        _append_assistant(
            state,
            "我已记录这个问题。当前结论仍以已确认事实和侧栏规则为边界；"
            "请补充你希望调整的具体字段或结论，或者回复“确认”继续。",
        )
        return
    if intent == DialogueIntent.REJECT:
        _append_assistant(state, "当前讨论块未确认。请直接说明不认可的结论和期望修改方向。")
        return
    if _looks_like_product_fact_revision(text):
        _handle_fact_revision_message(state, text, settings)
        return
    state.creation_session.brief = state.creation_session.brief.model_copy(
        update={
            "notes": (state.creation_session.brief.notes + "\n阶段修改意见：" + text).strip()
        }
    )
    state.creation_session = _run_stage_with_react(
        state,
        settings=settings,
        trigger="用户提交了当前阶段的修改意见",
    )
    _append_assistant(state, "已按你的修改意见重新生成当前阶段。")
    _open_stage_blocks(state)


def _start_workflow(state: ConversationGraphState, settings: Settings) -> None:
    _sync_brief(state, reset_session=True)
    state.creation_session = _run_stage_with_react(
        state,
        settings=settings,
        trigger="事实摘要已确认，开始工作流",
    )
    state.generated_fact_revision = state.facts_revision
    state.downstream_stale = False
    state.phase = "workflow"
    _open_stage_blocks(state)


def _run_stage_with_react(
    state: ConversationGraphState,
    *,
    settings: Settings,
    trigger: str,
) -> CreationSession:
    """Run one stage after a bounded ReAct plan/action/observation cycle."""
    session = state.creation_session
    stage = session.stage
    if stage == CreationStage.BRIEF and not session.brief.required_context_missing():
        stage = CreationStage.AUDIENCE
    research, turn = run_react_turn(
        stage=stage,
        trigger=trigger,
        brief=session.brief,
        confirmed_facts=state.confirmed_candidates(),
        settings=settings,
    )
    _record_react_turn(state, turn)
    return run_stage(session, settings=settings, research_context=research)


def _approve_stage_with_react(
    state: ConversationGraphState,
    *,
    settings: Settings,
) -> CreationSession:
    """Plan tools for the next stage before advancing the approval gate."""
    session = state.creation_session
    current = session.stage
    if current in {
        CreationStage.FINAL_COPY,
        CreationStage.IMAGE_HANDOFF,
        CreationStage.IMAGE_ANALYSIS,
        CreationStage.IMAGE_PLAN,
    }:
        return approve_stage(session, settings=settings)
    next_workflow_stage = next_stage(current)
    research, turn = run_react_turn(
        stage=next_workflow_stage,
        trigger=f"已确认 {current.value} 阶段，准备进入 {next_workflow_stage.value}",
        brief=session.brief,
        confirmed_facts=state.confirmed_candidates(),
        settings=settings,
    )
    _record_react_turn(state, turn)
    return approve_stage(session, settings=settings, research_context=research)


def _record_react_turn(state: ConversationGraphState, turn: Any) -> None:
    """Persist only plan actions and observations; never persist hidden reasoning."""
    state.react_turns.append(turn)
    for observation in turn.observations:
        state.research_activity.append(
            f"ReAct · {observation.tool.value} · {observation.status}：{observation.summary_zh}"
        )


def _open_stage_blocks(state: ConversationGraphState) -> None:
    artifact = state.creation_session.artifact(state.creation_session.stage)
    if artifact is None:
        _append_assistant(state, state.creation_session.last_message_zh or "当前阶段没有可讨论产物。")
        return
    blocks = blocks_for_artifact(artifact)
    state.discussion_blocks = [
        item for item in state.discussion_blocks if item.stage != artifact.stage.value
    ] + blocks
    state.current_block_id = blocks[0].block_id if blocks else ""
    state.research_activity.append(
        f"{artifact.stage.value} 阶段已执行按需研究路由；"
        f"规则文件 {len(state.creation_session.active_rule_files)} 个"
    )
    if blocks:
        _append_assistant(
            state,
            block_markdown(blocks[0], artifact),
            stage=artifact.stage.value,
            block_id=blocks[0].block_id,
            attachments=({"type": "stage_payload", "payload": artifact.payload},),
        )


def _confirm_current_block(state: ConversationGraphState, settings: Settings) -> None:
    block = state.current_block()
    if block is None:
        _append_assistant(state, "当前没有等待确认的讨论块。")
        return
    confirmed = block.model_copy(
        update={
            "status": DiscussionStatus.CONFIRMED,
            "confirmed_revision": block.revision,
        }
    )
    state.discussion_blocks = [
        confirmed if item.block_id == block.block_id else item
        for item in state.discussion_blocks
    ]
    stage_blocks = [item for item in state.discussion_blocks if item.stage == block.stage]
    next_block = next(
        (item for item in stage_blocks if item.status == DiscussionStatus.PENDING),
        None,
    )
    artifact = state.creation_session.artifact(CreationStage(block.stage))
    if next_block is not None and artifact is not None:
        active = next_block.model_copy(update={"status": DiscussionStatus.ACTIVE})
        state.discussion_blocks = [
            active if item.block_id == active.block_id else item
            for item in state.discussion_blocks
        ]
        state.current_block_id = active.block_id
        _append_assistant(
            state,
            block_markdown(active, artifact),
            stage=active.stage,
            block_id=active.block_id,
            attachments=({"type": "stage_payload", "payload": artifact.payload},),
        )
        return

    state.creation_session = _approve_stage_with_react(state, settings=settings)
    if state.creation_session.stage == CreationStage.COMPLETED:
        state.phase = "completed"
        state.current_block_id = ""
        _append_assistant(state, state.creation_session.last_message_zh or "流程已完成。")
        return
    _open_stage_blocks(state)


def _revise_fact(
    state: ConversationGraphState,
    fact_id: str,
    value: str,
) -> None:
    candidate = state.candidate(fact_id)
    clean = value.strip()
    if candidate is None or not clean:
        state.error = "fact_value_required"
        return
    replacement = candidate.model_copy(
        update={
            "value": clean,
            "status": CandidateStatus.PENDING,
            "revision": candidate.revision + 1,
            "confirmed_revision": 0,
            "confirmed_digest": "",
            "source_label": "human_revision",
            "source_quote": clean,
            "conflict_values": (),
        }
    )
    _replace_candidate(state, replacement)
    _invalidate_from_stage(state, dependency_start_for_fact(candidate.key))
    state.fact_summary_status = SummaryStatus.AWAITING_CONFIRMATION
    state.fact_summary_revision += 1
    state.phase = "fact_summary"
    _append_assistant(state, fact_summary_markdown(state.candidates))


def _invalidate_from_stage(state: ConversationGraphState, stage: CreationStage) -> None:
    if state.restart_stage:
        current = CreationStage(state.restart_stage)
        if STAGE_ORDER.index(current) < STAGE_ORDER.index(stage):
            stage = current
    affected = {
        item.value
        for item in STAGE_ORDER[STAGE_ORDER.index(stage) :]
    }
    state.discussion_blocks = [
        item.model_copy(update={"status": DiscussionStatus.STALE})
        if item.stage in affected
        else item
        for item in state.discussion_blocks
    ]
    state.downstream_stale = True
    state.stale_reason_zh = f"产品事实变化影响 {stage.value} 及后续阶段"
    state.restart_stage = stage.value


def _regenerate_from_current_facts(state: ConversationGraphState, settings: Settings) -> None:
    if state.fact_summary_status != SummaryStatus.CONFIRMED:
        _append_assistant(state, "请先在聊天中确认最新产品事实摘要。")
        return
    if state.downstream_stale and state.restart_stage:
        _resume_invalidated_workflow(state, settings)
    else:
        _start_workflow(state, settings)


def _resume_invalidated_workflow(
    state: ConversationGraphState,
    settings: Settings,
) -> None:
    """Regenerate only the earliest stage affected by revised product facts."""
    restart = CreationStage(state.restart_stage)
    restart_index = STAGE_ORDER.index(restart)
    _sync_brief(state)
    session = state.creation_session
    session.artifacts = {
        key: artifact
        for key, artifact in session.artifacts.items()
        if artifact.stage == CreationStage.BRIEF
        or STAGE_ORDER.index(artifact.stage) < restart_index
    }
    _refresh_brief_artifact(session)
    session.stage = restart
    session.status = "active"
    session.error = ""
    session.last_message_zh = ""
    session.deliverable = None
    session.claim_authorization = None
    session.image_design_plan = None
    session.image_design_requested = None
    session.human_review_confirmed = False
    session.revision += 1
    state.discussion_blocks = [
        item
        for item in state.discussion_blocks
        if STAGE_ORDER.index(CreationStage(item.stage)) < restart_index
    ]
    state.creation_session = _run_stage_with_react(
        state,
        settings=settings,
        trigger="已确认更新后的产品事实，恢复受影响阶段",
    )
    state.generated_fact_revision = state.facts_revision
    state.downstream_stale = False
    state.stale_reason_zh = ""
    state.restart_stage = ""
    state.phase = "workflow"
    _open_stage_blocks(state)


def _refresh_brief_artifact(session: CreationSession) -> None:
    """Keep the audit artifact synchronized while preserving prior approvals."""
    prior = session.artifact(CreationStage.BRIEF)
    if prior is None:
        return
    ledger_view = [
        {
            "fact": row.fact,
            "value": row.value or "—",
            "tier": row.tier.name,
            "source": row.source_kind.value,
            "status": row.status.value,
        }
        for row in session.brief.fact_ledger
    ]
    payload = dict(prior.payload)
    payload["brief"] = session.brief.model_dump(mode="json")
    payload["fact_ledger"] = ledger_view
    session.set_artifact(
        StageArtifact(
            stage=CreationStage.BRIEF,
            summary_zh=prior.summary_zh,
            payload=payload,
            approved=True,
            evidence_notes_zh=prior.evidence_notes_zh,
        )
    )


def _sync_brief(state: ConversationGraphState, *, reset_session: bool = False) -> None:
    confirmed = {item.key: item for item in state.confirmed_candidates()}
    ledger: list[FactRow] = []
    specs: list[str] = []
    variations: dict[str, str] = {}
    for item in state.confirmed_candidates():
        ledger.append(
            FactRow(
                fact=item.key,
                value=item.value,
                source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                source_label="human_summary_confirmation",
                status=FactStatus.VERIFIED,
                note=f"candidate={item.fact_id};revision={item.confirmed_revision}",
            )
        )
        if item.key.startswith("variation:") and item.value:
            variations[item.key.split(":", maxsplit=1)[1]] = item.value
        elif item.key not in _NON_SPEC_KEYS and item.value:
            specs.append(f"{item.label_zh}: {item.value}")

    text = " ".join(item.value for item in confirmed.values()).casefold()
    media = confirmed.get("media_category")
    scope = confirmed.get("listing_scope")
    competitors = confirmed.get("competitor_asins")
    brief = ProductBrief(
        product_name=_value(confirmed, "product_name"),
        marketplace=_value(confirmed, "marketplace"),
        language=_value(confirmed, "language") or "en",
        brand=_value(confirmed, "brand"),
        product_type=_value(confirmed, "product_type"),
        media_category=bool(media and media.value.casefold() in {"yes", "true", "是"}),
        media_status_confirmed=bool(media),
        listing_scope="child" if scope and scope.value.casefold() in {"child", "子体"} else "parent",
        listing_scope_confirmed=bool(scope),
        variation_values=variations,
        product_asin=_value(confirmed, "product_asin").upper(),
        specs_text="\n".join(specs),
        competitors=tuple(
            dict.fromkeys(re.findall(r"B0[A-Z0-9]{8}", competitors.value.upper()))
        )
        if competitors
        else (),
        notes=state.source_material,
        fact_ledger=tuple(ledger),
        sensitive_category=any(token in text for token in _SENSITIVE_TERMS),
    )
    if reset_session:
        state.creation_session = CreationSession(brief=brief)
    else:
        state.creation_session.brief = brief


def _value(rows: dict[str, FactCandidate], key: str) -> str:
    item = rows.get(key)
    return item.value if item and item.status == CandidateStatus.CONFIRMED else ""


def _replace_candidate(state: ConversationGraphState, replacement: FactCandidate) -> None:
    state.candidates = [
        replacement if item.fact_id == replacement.fact_id else item
        for item in state.candidates
    ]


def _append_user(state: ConversationGraphState, content: str) -> None:
    state.messages.append(ConversationMessage(role="user", content=content))


def _append_assistant(
    state: ConversationGraphState,
    content: str,
    *,
    stage: str = "",
    block_id: str = "",
    attachments: tuple[dict[str, Any], ...] = (),
) -> None:
    if content.strip():
        state.messages.append(
            ConversationMessage(
                role="assistant",
                content=content.strip(),
                stage=stage,
                block_id=block_id,
                attachments=attachments,
            )
        )


def _append_source_material(state: ConversationGraphState, content: str) -> bool:
    combined = (state.source_material + "\n" + content).strip()
    if len(combined.encode("utf-8")) > _MAX_SOURCE_BYTES:
        return False
    state.source_material = combined
    return True


def _contextual_intake_candidates(
    state: ConversationGraphState,
    text: str,
) -> list[FactCandidate]:
    """Interpret a short answer only when an intake field is awaiting a value.

    Marketplace codes intentionally require a label in long source material. In a
    chat turn whose sole purpose is filling a missing field, however, ``US`` is a
    valid direct answer and should not cause the full fact summary to be repeated.
    """
    clean = text.strip()
    if not clean or "\n" in clean or len(clean) > 120:
        return []
    existing = {item.key: item for item in state.candidates}
    missing = [item for item in state.candidates if item.required and not item.value.strip()]
    if not missing:
        return []

    marketplace = extract_short_marketplace_answer(clean)
    marketplace_candidate = existing.get("marketplace")
    if marketplace and (marketplace_candidate is None or not marketplace_candidate.value.strip()):
        rows = [_intake_answer_candidate(existing, "marketplace", marketplace, clean)]
        language_candidate = existing.get("language")
        if language_candidate is None or not language_candidate.value.strip():
            language = {
                "US": "en", "UK": "en-GB", "CA": "en-CA", "DE": "de", "FR": "fr",
                "IT": "it", "ES": "es", "JP": "ja", "MX": "es-MX",
            }.get(marketplace)
            if language:
                rows.append(_intake_answer_candidate(existing, "language", language, clean))
        return rows

    current = next(
        (item for item in state.candidates if item.fact_id == state.current_candidate_id),
        None,
    )
    if current is None or current.value.strip():
        current = min(missing, key=lambda item: (item.priority, item.group, item.label_zh))
    if current.key == "product_asin":
        asin = extract_short_asin_answer(clean)
        return [_intake_answer_candidate(existing, "product_asin", asin, clean)] if asin else []
    if current.key == "media_category":
        normalized = _normalize_media_answer(clean)
        return [_intake_answer_candidate(existing, current.key, normalized, clean)] if normalized else []
    if current.key == "listing_scope":
        normalized = _normalize_listing_scope_answer(clean)
        return [_intake_answer_candidate(existing, current.key, normalized, clean)] if normalized else []
    if current.key == "brand":
        generic = re.search(r"\bgeneric\b", clean, re.IGNORECASE)
        if generic:
            return [_intake_answer_candidate(existing, current.key, "generic", clean)]
    if _looks_like_field_statement(clean):
        return []
    if current.key in {"brand", "product_name", "product_type", "language", "media_category", "listing_scope"}:
        return [_intake_answer_candidate(existing, current.key, clean, clean)]
    return []


def _normalize_media_answer(value: str) -> str:
    clean = value.casefold()
    if clean in {"no", "false", "否"} or any(
        token in clean for token in ("不是媒体", "非媒体", "non-media", "not media")
    ):
        return "no"
    if clean in {"yes", "true", "是"} or "媒体类目" in clean:
        return "yes"
    return ""


def _normalize_listing_scope_answer(value: str) -> str:
    clean = value.casefold()
    if clean in {"child", "子体"} or "子体" in clean:
        return "child"
    if clean in {"parent", "父体"} or "父体" in clean:
        return "parent"
    return ""


def _looks_like_field_statement(value: str) -> bool:
    """Let deterministic extraction handle a sentence that names another field."""
    return bool(
        re.search(
            r"(?:产品名称|产品名|品牌|材质|尺寸|类目|产品类型|媒体|media|子体|父体|child|parent)",
            value,
            re.IGNORECASE,
        )
    )


def _handle_unavailable_intake_answer(
    state: ConversationGraphState,
    text: str,
) -> bool:
    """Keep unavailable answers out of the fact ledger and Listing inputs."""
    clean = " ".join(text.strip().casefold().split())
    if clean not in _UNAVAILABLE_ANSWERS:
        return False
    current = next(
        (item for item in state.candidates if item.fact_id == state.current_candidate_id),
        None,
    )
    if current is None or current.value.strip():
        return False
    if current.key in _IDENTITY_KEYS:
        _append_assistant(
            state,
            f"已记录你暂时无法提供“{current.label_zh}”。该字段属于启动工作流的必填身份信息，"
            "不能写入“未知”或猜测值。请提供实际值后继续。",
        )
        return True
    _append_assistant(
        state,
        f"已保留“{current.label_zh}”为待确认，不会写入 Listing。你可以继续补充其他字段，"
        "或在确认事实摘要后让系统在后续阶段明确标注该缺口。",
    )
    return True


def _intake_answer_candidate(
    existing: dict[str, FactCandidate],
    key: str,
    value: str,
    source_quote: str,
) -> FactCandidate:
    """Create a source-grounded update while retaining known field metadata."""
    prior = existing.get(key)
    if prior is not None:
        return prior.model_copy(
            update={
                "value": value,
                "source_label": "chat_field_answer",
                "source_quote": source_quote,
                "status": CandidateStatus.PENDING,
            }
        )
    return FactCandidate(
        fact_id=f"base:{key}",
        key=key,
        label_zh=key,
        value=value,
        question_zh=f"请确认{key}",
        source_label="chat_field_answer",
        source_quote=source_quote,
    )


def _append_contextual_intake_reply(
    state: ConversationGraphState,
    updates: list[FactCandidate],
) -> None:
    """Acknowledge one chat answer without re-rendering the whole summary."""
    recorded = "、".join(f"{item.label_zh}：{item.value}" for item in updates)
    _set_next_intake_candidate(state)
    remaining = [item for item in state.candidates if item.required and not item.value.strip()]
    if not remaining:
        _append_assistant(
            state,
            f"已记录 {recorded}。事实字段已补齐，请回复“确认”以确认整份产品事实摘要并进入市场调研。",
        )
        return
    current = next(
        (item for item in state.candidates if item.fact_id == state.current_candidate_id),
        min(remaining, key=lambda item: (item.priority, item.group, item.label_zh)),
    )
    _append_assistant(
        state,
        f"已记录 {recorded}。下一项请补充：{current.question_zh}\n\n"
        "你也可以一次补充其余字段，全部核对后回复“确认”。",
    )


def _set_next_intake_candidate(state: ConversationGraphState) -> None:
    """Keep a single explicit question target for terse follow-up answers."""
    missing = [item for item in state.candidates if item.required and not item.value.strip()]
    if not missing:
        state.current_candidate_id = ""
        state.pending_question_keys = ()
        return
    current = min(missing, key=lambda item: (item.priority, item.group, item.label_zh))
    state.current_candidate_id = current.fact_id
    state.pending_question_keys = tuple(item.key for item in missing)


def _should_ack_single_field_update(text: str, updates: list[FactCandidate]) -> bool:
    """Use an incremental response for one concise natural field statement."""
    return "\n" not in text.strip() and len(updates) == 1


def _looks_like_product_fact_revision(text: str) -> bool:
    """Keep stage feedback in its stage unless explicit product fields are supplied."""
    labels = (
        "产品",
        "产品名",
        "产品名称",
        "产品 asin",
        "asin",
        "站点",
        "marketplace",
        "品牌",
        "brand",
        "产品类型",
        "类目",
        "材质",
        "尺寸",
        "数量",
        "颜色",
        "重量",
        "容量",
        "兼容性",
        "认证",
        "质保",
        "父子体",
        "媒体类目",
        "竞品",
    )
    return any(
        re.search(rf"(?im)^\s*{re.escape(label)}\s*[:：=]", text)
        for label in labels
    )


__all__ = ["GraphChannels", "build_conversation_graph", "initial_graph_state"]
