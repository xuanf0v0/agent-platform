"""Tests for the rule-assisted, fully conversational creation workflow."""

from __future__ import annotations

import json
from pathlib import Path

from amazon_create.config import Settings
from amazon_create.conversation.graph import initial_graph_state
from amazon_create.conversation.reasoning import deterministic_candidates
from amazon_create.conversation.service import ConversationService
from amazon_create.schemas.conversation import CandidateStatus, SummaryStatus
from amazon_create.schemas.workflow import CreationStage
from streamlit.testing.v1 import AppTest

_COMPLETE_BRIEF = """产品: Mesh Zipper Pouch
产品 ASIN: B012345678
站点: US
语言: en
产品类型: zipper pouch
品牌: ACME
媒体类目: no
父子体: parent
材质: polyester
尺寸: 10 x 8 in
"""


def _service(path: Path) -> ConversationService:
    return ConversationService(Settings(MOCK=True, CHECKPOINT_PATH=path))


def _start_workflow(service: ConversationService):
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    snapshot = service.send_message(thread_id, _COMPLETE_BRIEF)
    return service.send_message(thread_id, "确认")


def test_long_brief_produces_one_fact_summary_without_interrupt(tmp_path: Path) -> None:
    service = _service(tmp_path / "conversation.sqlite3")
    snapshot = service.create_session()
    snapshot = service.send_message(snapshot.state.thread_id, _COMPLETE_BRIEF)

    assert snapshot.interrupt is None
    assert snapshot.state.phase == "fact_summary"
    assert snapshot.state.fact_summary_status == SummaryStatus.AWAITING_CONFIRMATION
    assert snapshot.state.confirmed_candidates() == []
    assert "产品事实摘要" in snapshot.state.messages[-1].content
    values = {item.key: item.value for item in snapshot.state.summary_facts()}
    assert values["product_asin"] == "B012345678"
    assert values["marketplace"] == "US"
    assert values["material"] == "polyester"


def test_one_chat_confirmation_confirms_all_sourced_facts(tmp_path: Path) -> None:
    service = _service(tmp_path / "confirm.sqlite3")
    snapshot = _start_workflow(service)

    confirmed = {item.key: item for item in snapshot.state.confirmed_candidates()}
    assert snapshot.interrupt is None
    assert snapshot.state.phase == "workflow"
    assert snapshot.state.creation_session.stage == CreationStage.AUDIENCE
    assert snapshot.state.current_block_id == "audience:1"
    assert {"product_asin", "marketplace", "material", "size"}.issubset(confirmed)
    assert all(item.is_confirmed_current for item in confirmed.values())
    assert snapshot.state.creation_session.artifact(CreationStage.BRIEF).approved


def test_missing_identity_fields_are_asked_together_in_chat(tmp_path: Path) -> None:
    service = _service(tmp_path / "missing.sqlite3")
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    snapshot = service.send_message(thread_id, "产品 ASIN: B012345678\n站点: US")
    snapshot = service.send_message(thread_id, "确认")

    assert snapshot.state.phase == "facts"
    assert {"product_name", "product_type", "brand"}.issubset(
        snapshot.state.pending_question_keys
    )
    reply = snapshot.state.messages[-1].content
    assert "请在一条消息中尽量补齐" in reply
    assert "产品名称" in reply
    assert "品牌" in reply


def test_unstructured_long_prompt_extracts_all_atomic_facts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    atomic = [f"fact value {index}" for index in range(40)]
    prompt = (
        "Create a listing for the Mesh Travel Pouch by ACME for the US marketplace in English. "
        "It is a non-media parent listing. Product category is zipper pouch. "
        + " ".join(atomic)
    )
    facts = [
        {
            "key": "product_name",
            "label_zh": "产品名称",
            "value": "Mesh Travel Pouch",
            "group": "基础信息",
            "required": True,
            "question_zh": "确认产品名称",
            "rationale_zh": "source",
            "source_quote": "Mesh Travel Pouch",
        },
        {
            "key": "marketplace",
            "label_zh": "目标站点",
            "value": "US",
            "group": "基础信息",
            "required": True,
            "question_zh": "确认站点",
            "rationale_zh": "source",
            "source_quote": "US marketplace",
        },
        {
            "key": "language",
            "label_zh": "目标语言",
            "value": "English",
            "group": "基础信息",
            "required": True,
            "question_zh": "确认语言",
            "rationale_zh": "source",
            "source_quote": "English",
        },
        {
            "key": "product_type",
            "label_zh": "产品类型",
            "value": "zipper pouch",
            "group": "基础信息",
            "required": True,
            "question_zh": "确认类目",
            "rationale_zh": "source",
            "source_quote": "zipper pouch",
        },
        {
            "key": "brand",
            "label_zh": "品牌",
            "value": "ACME",
            "group": "基础信息",
            "required": True,
            "question_zh": "确认品牌",
            "rationale_zh": "source",
            "source_quote": "ACME",
        },
        {
            "key": "media_category",
            "label_zh": "Media",
            "value": "non-media",
            "group": "合规范围",
            "required": True,
            "question_zh": "确认 media",
            "rationale_zh": "source",
            "source_quote": "non-media",
        },
        {
            "key": "listing_scope",
            "label_zh": "范围",
            "value": "parent",
            "group": "合规范围",
            "required": True,
            "question_zh": "确认范围",
            "rationale_zh": "source",
            "source_quote": "parent listing",
        },
    ]
    facts.extend(
        {
            "key": f"feature_{index}",
            "label_zh": f"事实 {index}",
            "value": value,
            "group": "规格参数",
            "required": True,
            "question_zh": f"确认事实 {index}",
            "rationale_zh": "source",
            "source_quote": value,
        }
        for index, value in enumerate(atomic)
    )

    class FactLLM:
        def complete(self, _system: str, _user: str, **_kwargs: object) -> str:
            return json.dumps({"facts": facts})

    monkeypatch.setattr(
        "amazon_create.conversation.reasoning.get_llm",
        lambda *_args, **_kwargs: FactLLM(),
    )
    service = _service(tmp_path / "long-prompt.sqlite3")
    snapshot = service.create_session()
    snapshot = service.send_message(snapshot.state.thread_id, prompt)

    values = {item.key: item.value for item in snapshot.state.candidates}
    assert values["product_name"] == "Mesh Travel Pouch"
    assert values["marketplace"] == "US"
    assert values["listing_scope"] == "parent"
    assert len([key for key in values if key.startswith("feature_")]) == 40
    assert snapshot.state.fact_summary_status == SummaryStatus.AWAITING_CONFIRMATION
    assert snapshot.interrupt is None


def test_chat_confirmations_advance_discussion_blocks_and_stages(tmp_path: Path) -> None:
    service = _service(tmp_path / "blocks.sqlite3")
    snapshot = _start_workflow(service)
    thread_id = snapshot.state.thread_id

    expected_audience_blocks = ["audience:1", "audience:2", "audience:3", "audience:4"]
    assert snapshot.state.current_block_id == expected_audience_blocks[0]
    for expected in expected_audience_blocks[1:]:
        snapshot = service.send_message(thread_id, "确认")
        assert snapshot.state.current_block_id == expected

    snapshot = service.send_message(thread_id, "确认")
    assert snapshot.state.creation_session.stage == CreationStage.PRODUCT
    assert snapshot.state.current_block_id == "product:1"
    assert all(
        item.status.value == "confirmed"
        for item in snapshot.state.discussion_blocks
        if item.stage == CreationStage.AUDIENCE.value
    )


def test_full_conversation_keeps_keywords_and_twenty_section_final_report(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "complete.sqlite3")
    snapshot = _start_workflow(service)
    thread_id = snapshot.state.thread_id
    visited: list[tuple[CreationStage, str]] = []

    for _ in range(24):
        visited.append((snapshot.state.creation_session.stage, snapshot.state.current_block_id))
        if snapshot.state.phase == "completed":
            break
        snapshot = service.send_message(thread_id, "确认")

    stages = [stage for stage, _block in visited]
    deliverable = snapshot.state.creation_session.deliverable
    assert CreationStage.KEYWORDS in stages
    assert (CreationStage.KEYWORDS, "keywords:1") in visited
    assert (CreationStage.KEYWORDS, "keywords:2") in visited
    assert CreationStage.FINAL_COPY in stages
    assert snapshot.state.phase == "completed"
    assert snapshot.state.creation_session.stage == CreationStage.COMPLETED
    assert deliverable is not None
    assert len(deliverable.final_report) == 20
    assert "二十、可直接上传的最终版本" in deliverable.final_report
    assert deliverable.title
    assert len(deliverable.bullets) == 5


def test_stage_feedback_regenerates_stage_without_mutating_product_facts(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "feedback.sqlite3")
    snapshot = _start_workflow(service)
    thread_id = snapshot.state.thread_id
    before = [(item.key, item.value, item.revision) for item in snapshot.state.candidates]

    snapshot = service.send_message(
        thread_id,
        "核心受众应优先考虑小型办公室采购者，请重新整理这一块",
    )

    after = [(item.key, item.value, item.revision) for item in snapshot.state.candidates]
    assert after == before
    assert snapshot.state.phase == "workflow"
    assert snapshot.state.creation_session.stage == CreationStage.AUDIENCE
    assert snapshot.state.current_block_id == "audience:1"
    assert "阶段修改意见" in snapshot.state.creation_session.brief.notes


def test_fact_revision_restarts_only_the_earliest_dependent_stage(tmp_path: Path) -> None:
    service = _service(tmp_path / "revision.sqlite3")
    snapshot = _start_workflow(service)
    thread_id = snapshot.state.thread_id
    for _ in range(4):
        snapshot = service.send_message(thread_id, "确认")
    assert snapshot.state.creation_session.stage == CreationStage.PRODUCT
    old_audience = snapshot.state.creation_session.artifact(CreationStage.AUDIENCE)

    snapshot = service.send_message(thread_id, "材质: nylon")
    assert snapshot.state.phase == "fact_summary"
    assert snapshot.state.downstream_stale
    assert snapshot.state.restart_stage == CreationStage.PRODUCT.value
    material = next(item for item in snapshot.state.candidates if item.key == "material")
    assert material.value == "nylon"
    assert material.status == CandidateStatus.PENDING

    snapshot = service.send_message(thread_id, "确认")
    material = next(item for item in snapshot.state.confirmed_candidates() if item.key == "material")
    assert material.value == "nylon"
    assert snapshot.state.creation_session.stage == CreationStage.PRODUCT
    assert snapshot.state.current_block_id == "product:1"
    assert snapshot.state.creation_session.artifact(CreationStage.AUDIENCE) == old_audience
    assert snapshot.state.creation_session.artifact(CreationStage.AUDIENCE).approved
    assert not snapshot.state.downstream_stale
    assert snapshot.state.restart_stage == ""


def test_research_starts_only_when_the_first_relevant_stage_opens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_research(_settings, **kwargs):
        calls.append(kwargs)
        return {
            "mode": "live",
            "marketplace": kwargs["marketplace"],
            "allowed_keywords": [],
            "market_metrics": [],
            "cited_evidence": [],
            "asin_research": [],
            "category_research": {},
            "gaps": [],
        }

    monkeypatch.setattr("amazon_create.conversation.react.load_research_context", fake_research)
    monkeypatch.setattr(
        "amazon_create.conversation.react.load_asin_research_context",
        lambda _settings, *, asin, marketplace: {
            "mode": "live",
            "asin": asin,
            "marketplace": marketplace,
            "product_attributes": [],
            "gaps": [],
        },
    )
    service = _service(tmp_path / "research.sqlite3")
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    snapshot = service.send_message(thread_id, _COMPLETE_BRIEF)
    assert calls == []

    snapshot = service.send_message(thread_id, "确认")
    assert len(calls) == 1
    assert calls[0]["product_name"] == "Mesh Zipper Pouch"
    assert calls[0]["marketplace"] == "US"
    assert snapshot.state.creation_session.stage == CreationStage.AUDIENCE
    assert snapshot.state.research_activity
    turn = snapshot.state.react_turns[-1]
    assert [action.tool.value for action in turn.actions] == [
        "market_research",
        "asin_research",
    ]
    assert all("Thought" not in observation.summary_zh for observation in turn.observations)


def test_react_rejects_unapproved_model_tool_and_keeps_stage_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class UnsafePlanner:
        def complete(self, _system: str, _user: str, **_kwargs: object) -> str:
            return '{"actions":[{"tool":"delete_database"},{"tool":"continue"}]}'

    monkeypatch.setattr(
        "amazon_create.conversation.react.get_llm",
        lambda *_args, **_kwargs: UnsafePlanner(),
    )
    calls: list[dict[str, object]] = []

    def fake_research(_settings, **kwargs):
        calls.append(kwargs)
        return {
            "mode": "live",
            "marketplace": kwargs["marketplace"],
            "allowed_keywords": [],
            "market_metrics": [],
            "cited_evidence": [],
            "asin_research": [],
            "category_research": {},
            "gaps": [],
        }

    monkeypatch.setattr("amazon_create.conversation.react.load_research_context", fake_research)
    monkeypatch.setattr(
        "amazon_create.conversation.react.load_asin_research_context",
        lambda *_settings, **_kwargs: {"mode": "unavailable", "product_attributes": []},
    )
    service = _service(tmp_path / "react-whitelist.sqlite3")
    snapshot = _start_workflow(service)

    assert snapshot.state.creation_session.stage == CreationStage.AUDIENCE
    assert snapshot.state.current_block_id == "audience:1"
    assert calls
    assert {item.tool.value for item in snapshot.state.react_turns[-1].actions} == {
        "market_research",
        "asin_research",
    }
    assert all(
        item.tool.value in {"market_research", "asin_research", "continue"}
        for item in snapshot.state.react_turns[-1].actions
    )


def test_stream_message_persists_only_complete_messages(tmp_path: Path) -> None:
    service = _service(tmp_path / "stream.sqlite3")
    snapshot = service.create_session()
    thread_id = snapshot.state.thread_id
    before_count = len(snapshot.state.messages)

    snapshot, chunks = service.stream_message(thread_id, _COMPLETE_BRIEF, chunk_chars=17)
    rendered = "".join(chunks)
    new_messages = snapshot.state.messages[before_count:]
    assistant = [item.content for item in new_messages if item.role == "assistant"]

    assert rendered == "\n\n".join(assistant)
    assert new_messages
    assert all(item.status == "complete" for item in new_messages)
    assert all(item.status != "streaming" for item in service.snapshot(thread_id).state.messages)


def test_stream_turn_emits_progress_before_complete_reply(tmp_path: Path) -> None:
    service = _service(tmp_path / "stream-turn.sqlite3")
    snapshot = service.create_session()

    events = list(service.stream_turn(snapshot.state.thread_id, _COMPLETE_BRIEF, chunk_chars=17))

    assert any(event.kind == "status" for event in events)
    assert any(event.kind == "text" for event in events)
    assert events[-1].kind == "done"
    persisted = service.snapshot(snapshot.state.thread_id)
    assert persisted.state.messages[-1].role == "assistant"
    assert persisted.state.messages[-1].status == "complete"


def test_legacy_conversation_is_read_only(tmp_path: Path) -> None:
    service = _service(tmp_path / "legacy.sqlite3")
    legacy = initial_graph_state("legacy-thread")
    legacy.schema_version = 1
    service._graph.invoke(
        {"data": legacy.model_dump(mode="json"), "action": {"type": "start"}},
        service._config(legacy.thread_id),
    )
    before = service.snapshot(legacy.thread_id)

    after = service.send_message(legacy.thread_id, _COMPLETE_BRIEF)

    assert after.state.is_legacy
    assert after.state.messages == before.state.messages
    assert after.state.phase == before.state.phase


def test_streamlit_page_uses_chat_as_the_only_business_control(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHECKPOINT_PATH", str(tmp_path / "ui.sqlite3"))
    monkeypatch.setenv("MOCK", "true")
    app_path = Path(__file__).parents[1] / "amazon_create" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30)
    app.run()

    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    assert "对话式 Listing 创作 Agent" in markdown
    assert "已确认事实" in markdown
    assert len(app.chat_input) == 1
    assert "确认事实" not in {button.label for button in app.button}

    app.chat_input[0].set_value(_COMPLETE_BRIEF).run()
    markdown = "\n".join(item.value for item in app.markdown)
    assert "产品事实摘要" in markdown

    app.chat_input[0].set_value("确认").run()
    rendered = "\n".join(
        [*(item.value for item in app.markdown), *(item.value for item in app.caption)]
    )
    assert not app.exception
    assert "类目市场概况" in rendered
    assert "产品 ASIN" in rendered
    assert "B012345678" in rendered
    assert "ReAct 研究记录" in rendered


def test_sellersprite_report_does_not_infer_marketplace_or_product_asin() -> None:
    report = """细分类目
Hanging Wall Files | SellerSprite,US,ASIN详情|
目标子体|Black / 5 Tier / Item | SellerSprite, BODSMRXZKKI
当前价格|$17.88 SellerSprite ASIN详情,2026-07-27快照|
核心市场词|'wall file organizer'|SIF关键词信号|
核心词市场估算量|约32,700/月|SIF关键词竞争,市场口径|
"""

    values = {item.key: item.value for item in deterministic_candidates(report)}

    assert "marketplace" not in values
    assert "product_asin" not in values
    assert "wall file organizer" in report
