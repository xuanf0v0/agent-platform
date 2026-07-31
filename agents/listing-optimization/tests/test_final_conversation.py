from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, final

import amazon_copy.api as api_module
from amazon_copy.config import Settings
from amazon_copy.final_conversation import _system_prompt, process_final_turn
from amazon_copy.run_store import OptimizationRunStore, default_run_title

from tests.specialized_ui_support import SOURCE, awaiting_approval, completed

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@final
class DecisionLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses: list[dict[str, object]] = responses
        self.call_count: int = 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        return json.dumps(self.responses.pop(0), ensure_ascii=False)


@final
class RepairingDecisionLLM:
    def __init__(self) -> None:
        self.call_count = 0
        self.users: list[str] = []

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        self.call_count += 1
        self.users.append(user)
        if self.call_count == 1:
            return '{"title":"wrong contract"}'
        return json.dumps(
            {
                "action": "answer",
                "assistant_reply": "是的，当前终稿包含 5 条 Bullet Point。",
                "research_query": "",
                "facts": [],
                "listing": None,
            },
            ensure_ascii=False,
        )


@final
class MissingListingDecisionLLM:
    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        if self.call_count == 1:
            return json.dumps(
                {
                    "action": "modify",
                    "assistant_reply": "已修改。",
                    "listing": None,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "action": "answer",
                "assistant_reply": "请说明需要修改的具体字段。",
                "listing": None,
            },
            ensure_ascii=False,
        )


@final
class MisleadingAnswerDecisionLLM:
    def __init__(self, revised: dict[str, object]) -> None:
        self.call_count = 0
        self.revised = revised

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        if self.call_count == 1:
            return json.dumps(
                {
                    "action": "answer",
                    "assistant_reply": "已为您补充到5条完整要点。",
                    "listing": None,
                },
                ensure_ascii=False,
            )
        if self.call_count == 2:
            return json.dumps(
                {
                    "action": "modify",
                    "assistant_reply": "已补充为5条完整要点。",
                    "listing": self.revised,
                },
                ensure_ascii=False,
            )
        return '{"issues":[]}'


def test_final_conversation_prompt_has_only_its_own_output_contract() -> None:
    prompt = _system_prompt()

    assert '"action": "answer | modify | research | new_identity"' in prompt
    assert '"title": "..."' not in prompt
    assert "current_listing_diagnosis" in prompt
    assert "Do not reuse character counts" in prompt


def test_invalid_decision_contract_is_repaired_once() -> None:
    llm = RepairingDecisionLLM()

    turn = process_final_turn(
        SOURCE,
        completed(),
        [],
        "这不是有五条吗？",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.reply == "是的，当前终稿包含 5 条 Bullet Point。"
    assert llm.call_count == 2
    assert "OUTPUT_REPAIR_REQUIRED" in llm.users[1]


def test_incomplete_modify_action_is_repaired_once() -> None:
    llm = MissingListingDecisionLLM()

    turn = process_final_turn(
        SOURCE,
        completed(),
        [],
        "帮我改一下",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.reply == "请说明需要修改的具体字段。"
    assert llm.call_count == 2


def test_answer_cannot_claim_a_draft_change_without_replacing_it() -> None:
    revised = {
        "title": "Painting River Rocks for Crafts",
        "item_highlights": "Smooth natural stones for creative projects",
        "bullets": [
            "Painting Surface: Smooth natural stones provide space for creative designs.",
            "Creative Projects: Add patterns, lettering, or artwork with suitable supplies.",
            "Display Options: Use finished pieces as desk accents or decorative markers.",
            "Craft Activities: Plan hands-on painting projects for home or group settings.",
            "Natural Variation: Shape, color, and texture may differ between stones.",
        ],
        "backend_search_terms": "pebble art garden markers keepsake",
    }
    llm = MisleadingAnswerDecisionLLM(revised)

    turn = process_final_turn(
        SOURCE,
        completed(),
        [
            {
                "role": "assistant",
                "content": "当前只有2条，需要我补充到5条吗？",
            }
        ],
        "补充",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.changed is True
    assert len(turn.result.listing.bullets) == 5
    assert llm.call_count == 3


def test_answer_turn_does_not_replace_release_ready_listing() -> None:
    baseline = completed()
    llm = DecisionLLM(
        [
            {
                "action": "answer",
                "assistant_reply": "标题当前为 58 个字符。",
                "research_query": "",
                "facts": [],
                "listing": None,
            }
        ]
    )

    turn = process_final_turn(
        SOURCE,
        baseline,
        [],
        "标题有多长？",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.reply == "标题当前为 58 个字符。"
    assert turn.result == baseline
    assert turn.changed is False
    assert llm.call_count == 1


def test_quality_answer_may_describe_existing_optimized_state() -> None:
    reply = "当前终稿已优化五点长度，发布门禁仍然通过。"
    llm = DecisionLLM(
        [{"action": "answer", "assistant_reply": reply, "listing": None}]
    )

    turn = process_final_turn(
        SOURCE,
        completed(),
        [],
        "检查一下文案质量如何",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.reply == reply
    assert turn.changed is False
    assert llm.call_count == 1


def test_repeated_quality_assessment_is_repaired_against_current_listing() -> None:
    repeated = "当前终稿整体合规，但语义覆盖只命中2/5类购买决策任务。"
    llm = DecisionLLM(
        [
            {
                "action": "answer",
                "assistant_reply": repeated,
                "listing": None,
            },
            {
                "action": "answer",
                "assistant_reply": "重新检查当前终稿后：五点长度均在限制内，当前覆盖维度符合要求。",
                "listing": None,
            },
        ]
    )

    turn = process_final_turn(
        SOURCE,
        completed(),
        [{"role": "assistant", "content": repeated}],
        "检查一下文案质量如何",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.reply != repeated
    assert "重新检查当前终稿" in turn.reply
    assert llm.call_count == 2


def test_new_identity_turn_keeps_current_listing() -> None:
    baseline = completed()
    llm = DecisionLLM(
        [
            {
                "action": "new_identity",
                "assistant_reply": "这是不同商品，请新建一次优化。",
                "facts": [],
                "listing": None,
            }
        ]
    )

    turn = process_final_turn(
        SOURCE,
        baseline,
        [],
        "改成英国站的蛋糕盒",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.result == baseline
    assert turn.changed is False


def test_explicit_seller_fact_is_saved_even_without_a_rewrite() -> None:
    baseline = completed()
    llm = DecisionLLM(
        [
            {
                "action": "answer",
                "assistant_reply": "已记录包装数量。",
                "facts": [{"key": "pack_count", "value": "12 pieces", "sku_scope": "all"}],
                "listing": None,
            }
        ]
    )

    turn = process_final_turn(
        SOURCE,
        baseline,
        [],
        "确认每包是12件",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    claim = turn.result.evidence_bundle.user_claims[-1]
    assert claim.key == "pack_count"
    assert claim.value == "12 pieces"
    assert turn.changed is False


def test_modify_turn_replaces_draft_only_after_release_checks() -> None:
    baseline = completed()
    revised = {
        "title": "River Rocks for Painting and Crafts",
        "item_highlights": "Natural stones for painting, decor, and hands-on craft projects",
        "bullets": [
            "Natural Stone Selection: Each rock has its own shape and surface variation.",
            "Ready for Creative Ideas: Use the stones for painting and craft projects.",
            "Multiple Project Options: Create decor, markers, keepsakes, or art displays.",
            "Simple Craft Material: Pair the rocks with supplies suited to natural stone.",
            "Variation to Expect: Sizes, shapes, colors, and textures naturally differ.",
        ],
        "backend_search_terms": "pebble art kindness garden markers keepsake",
    }
    llm = DecisionLLM(
        [
            {
                "action": "modify",
                "assistant_reply": "已缩短标题并保留核心商品信息。",
                "facts": [],
                "listing": revised,
            },
            {"issues": []},
        ]
    )

    turn = process_final_turn(
        SOURCE,
        baseline,
        [],
        "把标题缩短一些",
        settings=Settings(MOCK=True),
        llm=llm,
    )

    assert turn.changed is True
    assert turn.result.listing.title == revised["title"]
    assert turn.result.rendered_text != baseline.rendered_text
    assert turn.result.diagnosis_report is not None
    title_check = next(
        item for item in turn.result.diagnosis_report.field_checks if item.field == "Title"
    )
    assert title_check.metric == f"{len(revised['title'])}/75 characters"
    assert llm.call_count == 2


def test_optimization_run_store_survives_reopen(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = OptimizationRunStore(database)
    first.save(
        "run-1",
        '{"run_id":"run-1","status":"completed"}',
        "2026-07-31",
        title="Rock Listing",
        status="completed",
    )
    first.close()

    reopened = OptimizationRunStore(database)
    try:
        assert reopened.load("run-1") == {"run_id": "run-1", "status": "completed"}
        assert reopened.delete("run-1") is True
        assert reopened.load("run-1") is None
    finally:
        reopened.close()


def test_run_history_is_sorted_renamed_and_permanently_deleted(tmp_path: Path) -> None:
    store = OptimizationRunStore(tmp_path / "history.sqlite3")
    try:
        store.save(
            "older",
            '{"run_id":"older","status":"failed"}',
            "2026-07-30T09:00:00Z",
            title="Older Listing",
            status="failed",
        )
        store.save(
            "newer",
            '{"run_id":"newer","status":"completed"}',
            "2026-07-31T09:00:00Z",
            title="Newer Listing",
            status="completed",
        )

        assert [item["run_id"] for item in store.list_summaries()] == ["newer", "older"]
        assert store.rename("older", "Renamed Listing", "2026-08-01T09:00:00Z") is True
        assert store.list_summaries()[0]["title"] == "Renamed Listing"
        assert store.delete("older") is True
        assert [item["run_id"] for item in store.list_summaries()] == ["newer"]
    finally:
        store.close()


def test_legacy_run_table_is_migrated_and_backfilled(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TABLE optimization_api_runs ("
            "run_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO optimization_api_runs VALUES (?, ?, ?, ?)",
            (
                "legacy",
                json.dumps(
                    {
                        "run_id": "legacy",
                        "source_text": "Title: Ceramic Vase\nBullet one",
                        "status": "needs_clarification",
                    }
                ),
                "2026-07-30",
                "2026-07-31",
            ),
        )

    store = OptimizationRunStore(database)
    try:
        assert store.list_summaries() == [
            {
                "run_id": "legacy",
                "title": "Ceramic Vase",
                "status": "needs_clarification",
                "created_at": "2026-07-30",
                "updated_at": "2026-07-31",
            }
        ]
    finally:
        store.close()


def test_default_run_title_uses_first_nonblank_listing_line() -> None:
    assert default_run_title("\n标题：Wooden Desk Organizer\nBullet") == "Wooden Desk Organizer"


def test_workflow_messages_survive_result_replacement_and_restore() -> None:
    run = api_module.RunState(
        "workflow-history",
        SOURCE,
        None,
        status="awaiting_approval",
        result=awaiting_approval(token="a" * 64),
    )

    api_module._archive_stage(run, "确认并生成上传稿")
    run.result = completed()
    run.status = "completed"
    restored = api_module.RunState.restore(run.durable_payload())

    assert restored.workflow_messages[0]["role"] == "assistant"
    assert restored.workflow_messages[0]["status"] == "awaiting_approval"
    assert restored.workflow_messages[0]["result"]["diagnosis_report"]
    assert restored.workflow_messages[1] == {
        "role": "user",
        "content": "确认并生成上传稿",
    }


def test_failed_final_turn_is_not_saved_as_assistant_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = api_module.RunState(
        "failed-chat",
        SOURCE,
        None,
        status="completed",
        result=completed(),
        chat_messages=[{"role": "user", "content": "这不是有五条吗？"}],
    )

    failure_message = "invalid decision"

    def fail_turn(*_args: object, **_kwargs: object) -> None:
        raise ValueError(failure_message)

    monkeypatch.setattr(api_module, "process_final_turn", fail_turn)
    monkeypatch.setattr(api_module, "_persist", lambda _run: None)

    api_module._execute_chat(run, "这不是有五条吗？")

    assert run.chat_messages == [{"role": "user", "content": "这不是有五条吗？"}]
    assert run.turn_status == "failed"
    assert [event["event"] for event in run.events] == [
        "chat_status",
        "chat_error",
        "done",
    ]


def test_optimization_history_api_lists_renames_and_deletes(tmp_path: Path) -> None:
    store = OptimizationRunStore(tmp_path / "api-history.sqlite3")
    previous_store = api_module._store
    previous_runs = api_module._runs
    try:
        api_module._store = store
        api_module._runs = {}
        run = api_module.RunState(
            "history-run",
            SOURCE,
            None,
            title="Original title",
            status="completed",
            result=completed(),
        )
        api_module._runs[run.run_id] = run
        api_module._persist(run)

        assert api_module.list_runs()[0]["title"] == "Original title"
        renamed = api_module.rename_run(
            run.run_id,
            api_module.RenameRequest(title="Renamed title"),
        )
        assert renamed["title"] == "Renamed title"
        assert api_module.list_runs()[0]["title"] == "Renamed title"
        api_module.delete_run(run.run_id)
        assert api_module.list_runs() == []
    finally:
        api_module._store = previous_store
        api_module._runs = previous_runs
        store.close()
