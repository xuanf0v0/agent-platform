from __future__ import annotations

import json
from typing import TYPE_CHECKING, final

from amazon_copy.config import Settings
from amazon_copy.final_conversation import process_final_turn
from amazon_copy.run_store import OptimizationRunStore

from tests.specialized_ui_support import SOURCE, completed

if TYPE_CHECKING:
    from pathlib import Path


@final
class DecisionLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses: list[dict[str, object]] = responses
        self.call_count: int = 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        return json.dumps(self.responses.pop(0), ensure_ascii=False)


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
    assert llm.call_count == 2


def test_optimization_run_store_survives_reopen(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = OptimizationRunStore(database)
    first.save("run-1", '{"run_id":"run-1","status":"completed"}', "2026-07-31")
    first.close()

    reopened = OptimizationRunStore(database)
    try:
        assert reopened.load("run-1") == {"run_id": "run-1", "status": "completed"}
        assert reopened.delete("run-1") is True
        assert reopened.load("run-1") is None
    finally:
        reopened.close()
