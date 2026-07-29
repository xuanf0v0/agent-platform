"""Streamlit staged listing creation workbench (approval + evidence gates)."""

from __future__ import annotations

# pyright: reportUnusedCallResult=false

import streamlit as st

from amazon_create.config import Settings
from amazon_create.pipeline.creation_pipeline import (
    apply_user_message,
    new_session,
    run_stage,
)
from amazon_create.schemas.workflow import STAGE_LABEL_ZH, CreationSession, CreationStage

_THEME = """
<style>
:root {
  --bg: #000000;
  --surface: #141414;
  --text: #ffffff;
  --muted: rgba(255,255,255,0.72);
  --cta: #e8702a;
  --border: rgba(255,255,255,0.14);
}
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg);
  color: var(--text);
}
</style>
"""


def _session() -> CreationSession:
    if "creation_session" not in st.session_state:
        st.session_state.creation_session = new_session()
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "我是 Amazon Listing 创作助手（**审批门 + 证据控制**）。\n\n"
                    "流程：Brief/事实台账 → 受众 → 产品解读 → 竞品 → 五大卖点 → "
                    "关键词意图库 → 最终文案 → 是否主图+7辅图。\n\n"
                    "请提供：产品: …\\n站点: US\\n规格: …\n\n"
                    "指令：`认可` / `跳过竞品` / `直接输出` / `需要图片` / `不需要图片`。"
                ),
            }
        ]
    return st.session_state.creation_session


def _settings() -> Settings:
    return Settings()


def _render_deliverable(session: CreationSession) -> None:
    d = session.deliverable
    if d is None:
        return
    st.subheader("成稿（可复制）")
    st.caption(
        f"Title {d.title_chars}/75 · Item Highlights {d.item_highlights_chars}/125 · "
        f"Search Terms {d.search_terms_bytes}/250 bytes · 政策 {d.policy_status}"
    )
    if d.policy_status == "BLOCK":
        st.error("证据/政策门拦截：不可作为上传终稿，请补事实或改写。")
    st.markdown("**Title**")
    st.code(d.title, language=None)
    if d.title_zh:
        st.caption(d.title_zh)
    st.markdown("**Item Highlights**")
    st.code(d.item_highlights, language=None)
    if d.item_highlights_zh:
        st.caption(d.item_highlights_zh)
    for i, b in enumerate(d.bullets, 1):
        st.markdown(f"**Bullet {i}**")
        st.code(b.text, language=None)
        if b.text_zh:
            st.caption(b.text_zh)
    st.markdown("**Search Terms**")
    st.code(d.search_terms, language=None)
    if d.unresolved:
        st.warning("待补: " + "；".join(d.unresolved))
    if d.policy_issues:
        with st.expander("政策 / 证据校验明细"):
            for issue in d.policy_issues:
                st.write(issue)


def main() -> None:
    st.set_page_config(page_title="Listing Creation", layout="wide")
    st.markdown(_THEME, unsafe_allow_html=True)
    st.title("Amazon Listing 创作")
    st.caption(
        "审批门：Brief → 受众 → 产品 → 竞品 → 卖点 → 关键词 → 成稿 → 图片交接"
    )

    session = _session()
    settings = _settings()

    with st.sidebar:
        st.header("审批进度")
        for line in session.gate_checklist_zh():
            st.text(line)
        st.divider()
        st.header("诊断")
        label = STAGE_LABEL_ZH.get(session.stage, session.stage.value)
        st.write(f"当前门: **{label}**")
        st.write(f"状态: `{session.status}` · rev {session.revision}")
        st.write(
            f"产品: {session.brief.product_name or '—'} / "
            f"{session.brief.marketplace or '—'}"
        )
        if session.deliverable is not None:
            st.write(f"政策: `{session.deliverable.policy_status}`")
        if session.claim_authorization is not None:
            auth = session.claim_authorization
            st.write(f"证据授权: `{'OK' if auth.allowed else 'BLOCK'}`")
        with st.expander("证据等级", expanded=False):
            for line in session.evidence_policy_zh():
                st.caption(line)
        with st.expander("事实台账", expanded=False):
            if not session.brief.fact_ledger:
                st.caption("（空）")
            for row in session.brief.fact_ledger[:24]:
                st.caption(
                    f"[{row.tier.name}] {row.fact}={row.value or '—'} "
                    f"({row.source_kind.value}/{row.status.value})"
                )
        if st.button("新建对话", use_container_width=True):
            st.session_state.creation_session = new_session()
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": "新对话已开始。请提供产品名和目标站点。",
                }
            ]
            st.rerun()
        if st.button("认可当前阶段", type="primary", use_container_width=True):
            updated = apply_user_message(session, "认可", settings=settings)
            st.session_state.creation_session = updated
            st.session_state.messages.append({"role": "user", "content": "认可"})
            st.session_state.messages.append(
                {"role": "assistant", "content": updated.last_message_zh}
            )
            st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    show_copy = session.deliverable is not None and session.stage in {
        CreationStage.FINAL_COPY,
        CreationStage.IMAGE_HANDOFF,
        CreationStage.COMPLETED,
    }
    if show_copy:
        _render_deliverable(session)

    prompt = st.chat_input(
        "Brief / 修改意见 / 认可 / 跳过竞品 / 直接输出 / 需要图片 / 不需要图片"
    )
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        updated = apply_user_message(session, prompt, settings=settings)
        if (
            updated.stage == CreationStage.BRIEF
            and updated.artifact(CreationStage.BRIEF) is None
            and updated.brief.is_ready
        ):
            updated = run_stage(updated, settings=settings)
        st.session_state.creation_session = updated
        st.session_state.messages.append(
            {"role": "assistant", "content": updated.last_message_zh or "已处理。"}
        )
        st.rerun()


if __name__ == "__main__":
    main()
