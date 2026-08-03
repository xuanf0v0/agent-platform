"""Conditional visual-guidance loading without changing ordinary turns."""

from __future__ import annotations

from pathlib import Path

from amazon_create.config import Settings
from amazon_create.conversation.freeform_graph import _system_prompt, stream_reply
from amazon_create.schemas.conversation import ConversationGraphState, ConversationMessage


def _message(role: str, content: str) -> ConversationMessage:
    return ConversationMessage(role=role, content=content)  # type: ignore[arg-type]


def test_ordinary_turn_keeps_original_system_prompt_byte_for_byte() -> None:
    root = Path(__file__).parents[1] / "amazon_create"
    prompt = (root / "prompts" / "agents" / "creation_agent.md").read_text(encoding="utf-8")
    workflow = (root / "resources" / "amazon-listing-creation" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    expected = f"{prompt}\n\n{workflow}"

    actual = _system_prompt([_message("user", "请优化这五点描述")])

    assert actual == expected
    assert _system_prompt() == expected


def test_explicit_visual_request_loads_amazon_storyboard_guidance() -> None:
    prompt = _system_prompt([_message("user", "继续做主图和七张辅图的视觉策划")])

    assert "Campaign Style Lock" in prompt
    assert "Feature -> Advantage -> Buyer Benefit -> Evidence" in prompt
    assert "1 main image + 7 secondary images" in prompt
    assert "cannot authorize materials" in prompt


def test_short_explicit_need_images_request_loads_guidance() -> None:
    prompt = _system_prompt([_message("user", "需要图片")])

    assert "Campaign Style Lock" in prompt


def test_affirmative_reply_loads_guidance_only_after_visual_handoff() -> None:
    visual_messages = [
        _message("assistant", "Listing 已确认，是否需要继续做图片设计？"),
        _message("user", "需要"),
    ]
    ordinary_messages = [
        _message("assistant", "是否继续完善关键词？"),
        _message("user", "需要"),
    ]

    assert "Campaign Style Lock" in _system_prompt(visual_messages)
    assert "Campaign Style Lock" not in _system_prompt(ordinary_messages)


def test_affirmative_reply_does_not_reuse_a_stale_visual_handoff() -> None:
    messages = [
        _message("assistant", "是否需要继续做图片设计？"),
        _message("user", "先完善关键词"),
        _message("user", "需要"),
    ]

    assert "Campaign Style Lock" not in _system_prompt(messages)


def test_negated_visual_request_does_not_load_guidance() -> None:
    prompt = _system_prompt([_message("user", "暂不需要图片设计，先完善 Listing")])

    assert "Campaign Style Lock" not in prompt


class _CountingLLM:
    def __init__(self, *, selection: tuple[str, dict[str, str]] | None = None) -> None:
        self.selection = selection
        self.stream_calls = 0
        self.tool_calls = 0

    def select_tool(self, _system: str, _user: str, _tools: list[dict[str, object]]):
        self.tool_calls += 1
        return self.selection

    def stream(self, _system: str, _user: str, **_kwargs: object):
        self.stream_calls += 1
        yield "ok"


def test_visual_guidance_does_not_add_llm_or_tool_calls(monkeypatch) -> None:
    selector = _CountingLLM()
    writer = _CountingLLM()
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.get_llm",
        lambda _settings, role: selector if role == "review" else writer,
    )
    state = ConversationGraphState(
        thread_id="visual-call-count",
        messages=[_message("user", "请做主图和七张辅图的视觉方案")],
    )

    assert "".join(stream_reply(state, Settings(MOCK=True))) == "ok"
    assert selector.tool_calls == 1
    assert writer.stream_calls == 1
