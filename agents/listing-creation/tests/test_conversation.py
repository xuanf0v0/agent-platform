"""Tests for the prompt-driven persistent creation conversation."""

from pathlib import Path

from amazon_create.config import Settings
from amazon_create.conversation.freeform_graph import stream_reply
from amazon_create.conversation.service import ConversationService
from amazon_create.schemas.conversation import (
    ConfirmedFact,
    ConversationGraphState,
    ConversationMessage,
)


def _service(path: Path) -> ConversationService:
    return ConversationService(Settings(MOCK=True, CHECKPOINT_PATH=path))


def test_new_session_has_no_fixed_assistant_message(tmp_path: Path) -> None:
    service = _service(tmp_path / "empty.sqlite3")
    snapshot = service.create_session()

    assert snapshot.state.messages == []
    assert snapshot.state.schema_version == 3


def test_every_user_message_is_answered_by_the_llm(tmp_path: Path) -> None:
    service = _service(tmp_path / "chat.sqlite3")
    snapshot = service.create_session()

    snapshot = service.send_message(snapshot.state.thread_id, "你需要哪些东西")

    assert snapshot.state.messages[-2].role == "user"
    assert snapshot.state.messages[-1].role == "assistant"
    assert snapshot.state.messages[-1].content == "我理解你的意思：你需要哪些东西"
    assert "candidates" not in snapshot.state.model_dump()
    assert snapshot.state.confirmed_facts == []


def test_explicit_user_product_facts_are_extracted_for_sidebar(tmp_path: Path) -> None:
    service = _service(tmp_path / "facts.sqlite3")
    snapshot = service.create_session()

    snapshot = service.send_message(
        snapshot.state.thread_id,
        "产品 ASIN：B0G4QSF8KV\n站点：US\n材质：Memory Foam\n产品尺寸：16x15x3 inches",
    )

    values = {fact.key: fact.value for fact in snapshot.state.confirmed_facts}
    assert values == {
        "asin": "B0G4QSF8KV",
        "marketplace": "US",
        "material": "Memory Foam",
        "size": "16x15x3 inches",
    }


def test_workflow_instructions_are_not_extracted_as_product_facts(tmp_path: Path) -> None:
    service = _service(tmp_path / "instructions.sqlite3")
    snapshot = service.create_session()

    snapshot = service.send_message(
        snapshot.state.thread_id,
        "首先让用户提供产品ASIN和站点，所有产品事实必须以用户资料为准。",
    )

    assert snapshot.state.confirmed_facts == []


def test_pending_message_is_visible_before_llm_processing(tmp_path: Path) -> None:
    service = _service(tmp_path / "stream.sqlite3")
    snapshot = service.create_session()
    snapshot = service.enqueue_message(snapshot.state.thread_id, "根据 ASIN 提取")

    assert snapshot.state.pending_user_message == "根据 ASIN 提取"
    assert snapshot.state.messages[-1].role == "user"

    events = list(service.stream_pending_turn(snapshot.state.thread_id))
    rendered = "".join(event.content for event in events if event.kind == "text")

    assert rendered == "我理解你的意思：根据 ASIN 提取"
    assert service.snapshot(snapshot.state.thread_id).state.pending_user_message == ""


def test_conversation_history_is_persisted(tmp_path: Path) -> None:
    service = _service(tmp_path / "history.sqlite3")
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    service.send_message(thread_id, "第一轮")
    service.send_message(thread_id, "第二轮")

    restored = service.snapshot(thread_id)

    assert [message.role for message in restored.state.messages] == [
        "user", "assistant", "user", "assistant"
    ]
    assert restored.state.messages[-1].content == "我理解你的意思：第二轮"


def test_session_history_is_renamed_and_retained_until_deleted(tmp_path: Path) -> None:
    database = tmp_path / "retained-history.sqlite3"
    service = _service(database)
    first = service.create_session()
    second = service.create_session()
    service.rename_session(first.state.thread_id, "手动标题")
    service.close()

    reopened = _service(database)
    try:
        rows = reopened.list_sessions()
        assert {row["thread_id"] for row in rows} == {
            first.state.thread_id,
            second.state.thread_id,
        }
        assert next(row for row in rows if row["thread_id"] == first.state.thread_id)[
            "title"
        ] == "手动标题"
        reopened.delete_session(first.state.thread_id)
        assert [row["thread_id"] for row in reopened.list_sessions()] == [
            second.state.thread_id
        ]
    finally:
        reopened.close()


def test_v2_session_payload_continues_as_freeform_chat(tmp_path: Path) -> None:
    service = _service(tmp_path / "legacy.sqlite3")
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    with service._lock:
        service._graph.invoke(
            {
                "data": {
                    "thread_id": thread_id,
                    "schema_version": 2,
                    "title": "旧会话",
                    "phase": "fact_summary",
                    "messages": [{"role": "user", "content": "旧资料"}],
                    "candidates": [{"key": "material", "value": "steel"}],
                },
                "action": {"type": "start"},
            },
            service._config(thread_id),
        )

    continued = service.send_message(thread_id, "直接自然回答我")

    assert continued.state.schema_version == 2
    assert [message.role for message in continued.state.messages[-2:]] == ["user", "assistant"]
    assert continued.state.messages[-1].content == "我理解你的意思：直接自然回答我"
    assert continued.state.model_dump().keys() == {
        "thread_id",
        "schema_version",
        "title", "asin",
        "messages",
        "confirmed_facts",
        "pending_user_message",
        "error",
    }


class _ToolSelectingLLM:
    def __init__(self, selection: tuple[str, dict] | None = None) -> None:
        self.selection = selection
        self.received_user = ""
        self.received_system = ""

    @property
    def call_count(self) -> int:
        return 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        self.received_system = system
        self.received_user = user
        return "自然回复"

    def stream(self, system: str, user: str, **kwargs: object):
        self.received_system = system
        self.received_user = user
        yield "自然"
        yield "回复"

    def select_tool(self, system: str, user: str, tools: list[dict]):
        self.received_system = system
        self.received_user = user
        return self.selection


def test_model_selected_asin_tool_result_reaches_streaming_writer(monkeypatch) -> None:
    selector = _ToolSelectingLLM(("asin_research", {"asin": "B08N5WRWNW", "marketplace": "US"}))
    writer = _ToolSelectingLLM()
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.get_llm",
        lambda _settings, role: selector if role == "review" else writer,
    )
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.load_asin_research_context",
        lambda _settings, **kwargs: {"mode": "live", "title": "Echo Dot", **kwargs},
    )
    state = ConversationGraphState(
        thread_id="asin-tool",
        messages=[ConversationMessage(role="user", content="查询 B08N5WRWNW 美国站")],
    )

    rendered = "".join(stream_reply(state, Settings(MOCK=True)))

    assert rendered == "自然回复"
    assert "明确 Amazon ASIN" in selector.received_system
    assert "CONVERSATION" in selector.received_user
    assert '"tool": "asin_research"' in writer.received_user
    assert '"title": "Echo Dot"' in writer.received_user


def test_asin_research_context_keeps_existing_and_current_product_facts(monkeypatch) -> None:
    selector = _ToolSelectingLLM(
        ("asin_research", {"asin": "B0G4QSF8KV", "marketplace": "US"})
    )
    writer = _ToolSelectingLLM()
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.get_llm",
        lambda _settings, role: selector if role == "review" else writer,
    )
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.load_asin_research_context",
        lambda _settings, **kwargs: {
            "mode": "live",
            "product_attributes": [
                {"key": "title", "value": "Ergonomic Seat Cushion"},
                {"key": "brand", "value": "ErgoNest"},
            ],
            **kwargs,
        },
    )
    state = ConversationGraphState(
        thread_id="asin-full-context",
        confirmed_facts=[
            ConfirmedFact(
                key="material",
                label="材质",
                value="Memory Foam",
                group="规格参数",
                source_quote="材质是 Memory Foam",
            )
        ],
        messages=[
            ConversationMessage(role="user", content="材质是 Memory Foam"),
            ConversationMessage(role="assistant", content="还需要 ASIN 和站点。"),
            ConversationMessage(
                role="user",
                content="ASIN B0G4QSF8KV，美国站，尺寸是 18 x 14 x 3 inches。",
            ),
        ],
    )

    rendered = "".join(stream_reply(state, Settings(MOCK=True)))

    assert rendered == "自然回复"
    assert "Memory Foam" in writer.received_user
    assert "18 x 14 x 3 inches" in writer.received_user
    assert "Ergonomic Seat Cushion" in writer.received_user
    assert "用户已确认事实、MCP 待确认候选、尚待补充信息" in writer.received_user
    assert "不得只输出 MCP 查询事实" in writer.received_user


def test_model_selected_market_tool_result_reaches_streaming_writer(monkeypatch) -> None:
    selector = _ToolSelectingLLM(
        ("market_research", {"product_name": "seat cushion", "marketplace": "US", "specs": "memory foam"})
    )
    writer = _ToolSelectingLLM()
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.get_llm",
        lambda _settings, role: selector if role == "review" else writer,
    )
    monkeypatch.setattr(
        "amazon_create.conversation.freeform_graph.load_research_context",
        lambda _settings, **kwargs: {"mode": "live", "keywords": ["office chair cushion"], **kwargs},
    )
    state = ConversationGraphState(
        thread_id="market-tool",
        messages=[ConversationMessage(role="user", content="研究美国坐垫市场")],
    )

    rendered = "".join(stream_reply(state, Settings(MOCK=True)))

    assert rendered == "自然回复"
    assert '"tool": "market_research"' in writer.received_user
    assert "office chair cushion" in writer.received_user
