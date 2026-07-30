"""Conversational Streamlit workbench for Amazon Listing creation."""

# pyright: reportUnusedCallResult=false

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from time import sleep

import streamlit as st
from amazon_create.config import Settings
from amazon_create.conversation.service import ConversationService
from amazon_create.schemas.conversation import (
    CandidateStatus,
    ConversationSnapshot,
    DiscussionStatus,
    SummaryStatus,
)
from amazon_create.schemas.deliverable import CreationDeliverable
from amazon_create.schemas.workflow import STAGE_LABEL_ZH, CreationStage
from amazon_create.ui.theme import THEME_CSS


@st.cache_resource
def _service() -> ConversationService:
    return ConversationService(Settings())


def _run_action(action: Callable[[], object]) -> None:
    try:
        action()
    except Exception as exc:  # noqa: BLE001
        st.error(f"操作失败：{exc}")
        return
    st.rerun()


def _active_thread(service: ConversationService) -> str:
    sessions = service.list_sessions()
    known = {item["thread_id"] for item in sessions}
    current = str(st.session_state.get("creation_thread_id") or "")
    if current in known:
        return current
    snapshot = service.create_session()
    st.session_state.creation_thread_id = snapshot.state.thread_id
    return snapshot.state.thread_id


def _render_session_manager(service: ConversationService, active_thread: str) -> None:
    sessions = service.list_sessions()
    titles = {item["thread_id"]: item["title"] for item in sessions}
    thread_ids = list(titles)
    selected = st.selectbox(
        "历史会话",
        thread_ids,
        index=thread_ids.index(active_thread),
        format_func=lambda value: titles.get(value, "新建 Listing"),
    )
    if selected != active_thread:
        st.session_state.creation_thread_id = selected
        st.rerun()
    left, right = st.columns(2)
    if left.button("新建", use_container_width=True):
        def create() -> None:
            snapshot = service.create_session()
            st.session_state.creation_thread_id = snapshot.state.thread_id

        _run_action(create)
    if right.button("删除", use_container_width=True):
        def delete() -> None:
            service.delete_session(active_thread)
            remaining = service.list_sessions()
            if remaining:
                st.session_state.creation_thread_id = remaining[0]["thread_id"]
            else:
                snapshot = service.create_session()
                st.session_state.creation_thread_id = snapshot.state.thread_id

        _run_action(delete)
    with st.expander("重命名会话"), st.form("rename-session"):
        title = st.text_input("名称", value=titles.get(active_thread, "新建 Listing"))
        if st.form_submit_button("保存", use_container_width=True):
            _run_action(lambda: service.rename_session(active_thread, title))


def _render_fact_sidebar(
    _service: ConversationService,
    snapshot: ConversationSnapshot,
) -> None:
    state = snapshot.state
    confirmed = state.confirmed_candidates()
    unresolved = state.unresolved_candidates()
    st.markdown("### 对话进度")
    summary_label = {
        SummaryStatus.COLLECTING: "等待产品资料",
        SummaryStatus.AWAITING_CONFIRMATION: "等待整体确认",
        SummaryStatus.CONFIRMED: "事实摘要已确认",
    }[state.fact_summary_status]
    st.caption(summary_label)
    current = state.current_block()
    if current:
        st.info(f"当前讨论：{current.title_zh}")
    stage_blocks = [
        item for item in state.discussion_blocks if item.stage == state.creation_session.stage.value
    ]
    if stage_blocks:
        for item in stage_blocks:
            mark = {
                DiscussionStatus.CONFIRMED: "✓",
                DiscussionStatus.ACTIVE: "▶",
                DiscussionStatus.STALE: "!",
                DiscussionStatus.PENDING: "○",
            }[item.status]
            st.write(f"{mark} {item.title_zh}")

    st.divider()
    st.markdown("### 待解决问题")
    if unresolved:
        grouped_pending: dict[str, list] = defaultdict(list)
        for item in unresolved:
            grouped_pending[item.group].append(item)
        for group, rows in grouped_pending.items():
            with st.expander(f"{group} · {len(rows)} 项", expanded=True):
                for item in rows:
                    status = "冲突" if item.status == CandidateStatus.CONFLICT else "待确认"
                    current = f" · 当前：{item.value}" if item.value else " · 缺失"
                    st.markdown(f"**○ {item.label_zh}** `{status}`{current}")
                    st.caption(item.question_zh)
                    if item.conflict_values:
                        st.warning("冲突值：" + " / ".join(item.conflict_values))
    else:
        st.success("暂无待解决问题")

    st.divider()
    st.markdown("### 已确认事实")
    if not confirmed:
        st.caption("确认事实摘要后显示。")
    else:
        groups: dict[str, list] = defaultdict(list)
        for item in confirmed:
            groups[item.group].append(item)
        for group, rows in groups.items():
            with st.expander(f"{group} · {len(rows)} 项"):
                for item in rows:
                    st.markdown(f"**✓ {item.label_zh}**")
                    st.caption(item.value)

    st.divider()
    st.markdown("### 规则辅助")
    for hit in state.rule_hits:
        st.write(f"• {hit}")
    if state.react_turns:
        st.divider()
        st.markdown("### ReAct 研究记录")
        for turn in state.react_turns[-4:]:
            labels = "、".join(action.label_zh for action in turn.actions)
            st.caption(f"{turn.stage} · {labels}")
            for observation in turn.observations:
                st.write(f"• {observation.summary_zh}")
    if state.research_activity:
        st.markdown("### 研究来源")
        for row in state.research_activity[-8:]:
            st.write(f"• {row}")


def _render_deliverable(deliverable: CreationDeliverable) -> None:
    st.markdown("## 可复制成稿")
    st.caption(
        f"Title {deliverable.title_chars}/75 · Highlights {deliverable.item_highlights_chars}/125 · "
        f"Search Terms {deliverable.search_terms_bytes}/250 bytes · {deliverable.policy_status}"
    )
    if deliverable.policy_status == "BLOCK":
        st.error("证据或政策门已拦截，当前内容不可作为上传终稿。")
    st.markdown("### 三套 Title 与 Item Highlights")
    for variant in deliverable.title_variants:
        with st.expander(
            f"版本 {variant.code} · {variant.strategy_zh} · {variant.title_chars}/75",
            expanded=variant.code == deliverable.recommended_variant,
        ):
            st.code(variant.title, language=None)
            st.caption(variant.title_zh)
            st.code(variant.item_highlights, language=None)
            st.caption(
                f"Item Highlights {variant.item_highlights_chars}/125 · "
                + "、".join(variant.primary_keywords)
            )
    st.markdown("### 可直接上传的最终版本")
    fields = [
        ("Title", deliverable.title, deliverable.title_zh),
        ("Item Highlights", deliverable.item_highlights, deliverable.item_highlights_zh),
    ]
    fields.extend(
        (f"Bullet {index}", bullet.text, bullet.text_zh)
        for index, bullet in enumerate(deliverable.bullets, 1)
    )
    fields.extend(
        [
            ("Product Description", deliverable.product_description, deliverable.product_description_zh),
            ("Backend Search Terms", deliverable.search_terms, ""),
        ]
    )
    for label, text, translation in fields:
        if not text:
            continue
        st.markdown(f"**{label}**")
        st.code(text, language=None)
        if translation:
            st.caption(translation)
        if label.startswith("Bullet"):
            bullet = deliverable.bullets[int(label.split()[-1]) - 1]
            st.caption(
                f"购买意图：{bullet.purchase_intent_zh or '待确认'} · "
                f"关键词：{'、'.join(bullet.covered_keywords) or '—'} · {bullet.chars} 字符"
            )
    with st.expander("语义、A+、类目与证据明细"):
        if deliverable.shopping_questions:
            st.markdown("### Rufus 问答覆盖")
            for item in deliverable.shopping_questions:
                st.markdown(f"**{item.question}**")
                st.write(
                    f"{'已覆盖' if item.listing_answered else '未覆盖'} · "
                    f"{item.location or '待分配'} · {item.clarity}"
                )
                st.caption(item.answer_basis)
        if deliverable.a_plus_modules:
            st.markdown("### A+ / EBC")
            for item in deliverable.a_plus_modules:
                st.markdown(f"**{item.module}** · {item.purpose}")
                st.write(item.content)
        if deliverable.category_recommendations:
            st.markdown("### 类目候选")
            for item in deliverable.category_recommendations:
                st.write(f"{item.path} · {item.node_id_path or '待查'} · {item.verification}")
        if deliverable.keyword_intent_map:
            st.markdown("### 关键词与意图布局")
            st.json(deliverable.keyword_intent_map)
        if deliverable.claim_evidence_map:
            st.markdown("### 宣称与证据")
            for item in deliverable.claim_evidence_map:
                st.write(f"{item.claim} → {item.source} · {item.status}")
        issues = [
            *deliverable.unresolved,
            *deliverable.compliance_notes,
            *deliverable.policy_issues,
        ]
        if issues:
            st.markdown("### 待补与合规")
            for issue in issues:
                st.write(f"• {issue}")
    if deliverable.final_report:
        with st.expander("完整二十段报告", expanded=False):
            for title, content in deliverable.final_report.items():
                st.markdown(f"### {title}")
                _render_payload(content)


def _render_payload(payload: object) -> None:
    """Render structured stage payloads as readable tables and sections."""
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            st.dataframe(payload, use_container_width=True, hide_index=True)
        elif payload:
            for item in payload:
                st.write(f"• {item}")
        else:
            st.caption("暂无可验证数据")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            st.markdown(f"**{key}**")
            _render_payload(value)
        return
    st.write(payload if payload not in {None, ""} else "待确认")


def _render_workflow_actions(service: ConversationService, snapshot: ConversationSnapshot) -> None:
    state = snapshot.state
    session = state.creation_session
    if state.downstream_stale:
        st.error(state.stale_reason_zh or "现有结果基于旧事实版本，终审已锁定。")
        st.caption("请先在聊天中确认最新事实摘要；系统会自动重新进入受影响阶段。")
        return
    if state.phase not in {"workflow", "completed"}:
        return
    stage = session.stage
    if stage == CreationStage.COMPLETED:
        st.success("文案与所选图片流程已完成。")
        return
    st.caption("所有业务确认、修改和阶段推进均通过底部聊天完成。")


def _render_stage_output(snapshot: ConversationSnapshot) -> None:
    session = snapshot.state.creation_session
    if session.deliverable:
        _render_deliverable(session.deliverable)
    if session.image_design_plan:
        st.markdown("## 主图 + 7 张辅图")
        st.dataframe(
            [item.model_dump(mode="json") for item in session.image_design_plan.images],
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="Listing 创作 Agent", page_icon="✨", layout="wide")
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    service = _service()
    active_thread = _active_thread(service)
    snapshot = service.snapshot(active_thread)
    state = snapshot.state

    with st.sidebar:
        st.markdown("## Listing 创作")
        _render_session_manager(service, active_thread)
        st.divider()
        _render_fact_sidebar(service, snapshot)

    st.markdown(
        "<section class='hero'><p class='eyebrow'>AMAZON LISTING CREATION · HUMAN VERIFIED</p>"
        "<h1>对话式 Listing 创作 Agent</h1>"
        "<p>整段输入，Agent 主导讨论；规则、事实、研究与阶段门禁持续辅助。</p></section>",
        unsafe_allow_html=True,
    )
    stage_label = STAGE_LABEL_ZH.get(
        state.creation_session.stage,
        state.creation_session.stage.value,
    )
    st.markdown(
        "<div class='status-strip'>"
        f"<span>会话 <strong>{state.title}</strong></span>"
        f"<span>阶段 <strong>{stage_label}</strong></span>"
        f"<span>事实版本 <strong>{state.facts_revision}</strong></span>"
        f"<span>状态 <strong>{state.phase}</strong></span>"
        "</div>",
        unsafe_allow_html=True,
    )
    if state.error:
        st.warning(state.error)
    if state.is_legacy:
        st.warning("该会话由旧架构创建，仅支持查看。请点击左侧“新建”进入全对话流程。")

    for message in state.messages:
        with st.chat_message(message.role):
            st.markdown(message.content)

    _render_workflow_actions(service, snapshot)
    _render_stage_output(snapshot)

    placeholder = "粘贴完整资料，或回复确认、修改意见和补充信息"
    prompt = st.chat_input(placeholder, max_chars=64000, disabled=state.is_legacy)
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
            st.caption("已发送")
        try:
            with st.chat_message("assistant"):
                progress = st.empty()
                progress.markdown(
                    "<div class='agent-typing'><span class='agent-typing-label'>Agent 正在响应</span>"
                    "<span class='typing-dots'><i></i><i></i><i></i></span></div>",
                    unsafe_allow_html=True,
                )
                response = st.empty()
                rendered = ""
                for event in service.stream_turn(state.thread_id, prompt, chunk_chars=32):
                    if event.kind == "status":
                        progress.markdown(
                            "<div class='agent-typing'>"
                            f"<span class='agent-typing-label'>{event.content}</span>"
                            "<span class='typing-dots'><i></i><i></i><i></i></span></div>",
                            unsafe_allow_html=True,
                        )
                    elif event.kind == "text":
                        progress.empty()
                        rendered += event.content
                        response.markdown(rendered + "▍")
                        sleep(0.018)
                    elif event.kind == "done":
                        progress.empty()
                        response.markdown(rendered)
        except Exception as exc:  # noqa: BLE001
            progress.empty()
            st.error(f"操作失败：{exc}")
        else:
            st.rerun()


if __name__ == "__main__":
    main()
