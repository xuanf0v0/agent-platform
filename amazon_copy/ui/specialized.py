"""Specialized-rule evidence and clarification widgets for the Streamlit UI."""

from __future__ import annotations

# Streamlit render calls intentionally return unused DeltaGenerator handles.
# pyright: reportUnusedCallResult=false
import html
import re
from typing import Final

import streamlit as st

from amazon_copy.automatic_models import (
    AwaitingApproval,
    CompletedOptimization,
    FailedOptimization,
    NeedsClarification,
)
from amazon_copy.mcp.security import sanitize_mcp_text
from amazon_copy.ui.view_models import format_specialized_rule_sections

RenderableOptimization = (
    CompletedOptimization | AwaitingApproval | NeedsClarification | FailedOptimization
)

_PRIVATE_URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_SAFE_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_NO_BREAK_PHRASES: Final[tuple[str, ...]] = (
    "“8 leather and water bags”",
    "并认可删除/降级原则",
    "直接删除或降级",
    "可以逐项回答",
    "若无法提供",
    "包装清单",
    "或卖家确认",
    "卖家确认",
    "卖家逐项确认",
    "逐项回答",
    "无法确认",
    "删除/降级原则",
    "该宣称",
    "请确认",
)


def _safe_identifier(value: str) -> str:
    """Return an allowlisted identifier suitable for rendering in the UI."""
    sanitized = _PRIVATE_URL_RE.sub("[已隐藏链接]", sanitize_mcp_text(value)).strip()
    return sanitized if _SAFE_IDENTIFIER_RE.fullmatch(sanitized) else "已隐藏标识"


def _semantic_html(value: str) -> str:
    protected = html.escape(value)
    for phrase in _NO_BREAK_PHRASES:
        protected = protected.replace(
            phrase,
            (
                '<span class="lithos-no-break" '
                'style="display:inline-block;white-space:nowrap!important">'
                f"{phrase}</span>"
            ),
        )
    return protected


def render_specialized_evidence(result: RenderableOptimization) -> None:
    """Render safe specialized profiles, hashes, gaps, and fallback status."""
    specialized_cache = result.specialized_rule_cache
    if specialized_cache is not None:
        with st.expander("专业规则配置", expanded=False):
            for _title, lines in format_specialized_rule_sections(
                specialized_cache,
                reused=result.specialized_cache_reused,
            ):
                for line in lines:
                    st.caption(line)

    rule_context = result.rule_context
    if rule_context is None or not rule_context.gaps:
        return
    with st.expander("规则依据与缺口", expanded=False):
        if rule_context.authoritative:
            rule_text = (
                "已使用后端提供的权威规则："
                f"{_safe_identifier(rule_context.marketplace)} · "
                f"{_safe_identifier(rule_context.product_type)}。"
            )
            st.caption(rule_text)
        else:
            st.caption("后端未提供权威类目规则；仅使用安全的默认限制，不把默认市场或类目当作事实。")
        st.caption("规则缺口：" + "、".join(gap.code for gap in rule_context.gaps))


def render_clarification(
    result: NeedsClarification,
) -> None:
    """Render active fact questions without separate form controls."""
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        st.markdown("### 优化前需要确认的事实")
        st.markdown(
            '<p class="lithos-confirm-copy">'
            + _semantic_html(
                "为了避免新版文案继续带入不实宣称，请确认以下项目；"
                "无法确认的会直接删除或降级："
            )
            + "</p>",
            unsafe_allow_html=True,
        )
        for index, question in enumerate(result.questions, start=1):
            question_text = _semantic_html(question.question_zh).replace(
                "Amazon Product Type",
                (
                    '<span class="lithos-no-break" '
                    'style="display:inline-block;white-space:nowrap!important">'
                    "Amazon Product Type</span>"
                ),
            )
            st.markdown(
                f'<p class="lithos-confirm-question">{index}. {question_text}</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="lithos-confirm-evidence">'
                + _semantic_html("所需依据：" + question.evidence_needed)
                + "</p>",
                unsafe_allow_html=True,
            )
        st.markdown(
            '<p class="lithos-confirm-footer">'
            + _semantic_html(
                "请直接在下方回复确认结果。可以逐项回答，"
                "也可以说明哪些无法确认并认可删除/降级原则。"
            )
            + "</p>",
            unsafe_allow_html=True,
        )


__all__ = [
    "RenderableOptimization",
    "render_clarification",
    "render_specialized_evidence",
]
