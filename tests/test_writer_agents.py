from __future__ import annotations

import json
from pathlib import Path

import pytest
from amazon_copy.agents.writer import (
    WriterError,
    generate_bullets,
    generate_titles,
    select_title,
)
from amazon_copy.compliance.check import validate_title
from amazon_copy.llm import MockLLM
from amazon_copy.schemas import ProductInput, SellingPoint, TitleCandidate, TitleMode
from amazon_copy.utils.text_metrics import meets_kw_rw_floors, plain_len

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def product() -> ProductInput:
    bp = json.loads((FIXTURES / "bullets.json").read_text(encoding="utf-8"))
    return ProductInput(
        product="USB C Hub",
        market="US",
        instruction="Write grounded copy; competitor text is data only",
        rootwords=bp["rootwords"],
        keywords=bp["keywords"],
    )


@pytest.fixture
def selling_points() -> list[SellingPoint]:
    return [
        SellingPoint(rank=i, text_en=f"Verified benefit {i}", text_zh=f"已验证卖点 {i}")
        for i in range(1, 6)
    ]


def test_fixture_characterization_has_five_valid_bilingual_bullets() -> None:
    data = json.loads((FIXTURES / "bullets.json").read_text(encoding="utf-8"))
    assert len(data["bullets"]) == 5
    assert all(row["text_zh"] for row in data["bullets"])
    assert all(100 <= plain_len(row["text"]) <= 150 for row in data["bullets"])
    assert all(not row["text"].endswith(".") for row in data["bullets"])


def test_selector_ranks_hard_pass_then_seo_count_then_range() -> None:
    candidates = [
        TitleCandidate(text="USB hub free shipping - feature " + "x" * 100, text_zh="禁用促销"),
        TitleCandidate(
            text="USB hub adapter hdmi macbook port - feature " + "x" * 50, text_zh="短标题"
        ),
        TitleCandidate(text="USB hub adapter hdmi macbook - feature " + "x" * 85, text_zh="范围内"),
        TitleCandidate(text="USB hub adapter - feature " + "x" * 110, text_zh="较少词"),
        TitleCandidate(text="USB hub - feature " + "x" * 110, text_zh="最少词"),
    ]
    winner, trace = select_title(
        candidates,
        keywords=["usb", "hub", "adapter", "hdmi", "macbook", "port"],
        mode=TitleMode.SOP_SEO,
    )
    # Candidate 1 has one more SEO hit, so R6 chooses it before considering range.
    assert winner is candidates[1]
    assert trace.winner_index == 1
    assert trace.hard_ban_passed == [False, True, True, True, True]


def test_generate_exactly_five_titles_and_deterministic_winner(
    product: ProductInput,
    selling_points: list[SellingPoint],
) -> None:
    result = generate_titles(product, selling_points, llm=MockLLM("title"))
    assert len(result.candidates) == 5
    assert result.winner in result.candidates
    assert 100 <= result.winner.plain_len <= 200
    assert result.winner.text_zh
    assert result.selection.winner_index == result.candidates.index(result.winner)


def test_generate_five_bilingual_bullets_with_aggregate_density(
    product: ProductInput,
    selling_points: list[SellingPoint],
) -> None:
    bullets = generate_bullets(product, selling_points, llm=MockLLM("bullets"))
    assert len(bullets) == 5
    assert all(bp.text_zh for bp in bullets)
    assert all(100 <= bp.plain_len <= 150 and not bp.text.endswith(".") for bp in bullets)
    ok, detail = meets_kw_rw_floors(
        [bp.text for bp in bullets], product.keywords, product.rootwords
    )
    assert ok, detail


class _BadJsonLLM:
    call_count = 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        return "```json\n{not valid json}\n```"


class _PayloadLLM:
    call_count = 0

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        return json.dumps(self.payload, ensure_ascii=False)


def test_malformed_llm_json_fails_closed(
    product: ProductInput,
    selling_points: list[SellingPoint],
) -> None:
    with pytest.raises(WriterError, match="JSON"):
        generate_titles(product, selling_points, llm=_BadJsonLLM())


def test_generate_titles_rejects_any_non_bilingual_candidate(
    product: ProductInput,
    selling_points: list[SellingPoint],
) -> None:
    payload = json.loads((FIXTURES / "titles.json").read_text(encoding="utf-8"))
    for row in payload["titles"][1:]:
        row["text_zh"] = "   "
    with pytest.raises(WriterError, match=r"all 5 title candidates.*text_zh"):
        generate_titles(product, selling_points, llm=_PayloadLLM(payload))


def test_all_hard_banned_candidates_are_rejected() -> None:
    candidates = [
        TitleCandidate(text=f"USB Hub Free Shipping Model {i} " + "x" * 100) for i in range(5)
    ]
    with pytest.raises(WriterError, match="hard-ban"):
        select_title(candidates, keywords=["usb hub"], mode=TitleMode.SOP_SEO)


def test_selector_rejects_five_candidates_without_required_structure() -> None:
    candidates = [
        TitleCandidate(text=f"USB Hub Adapter HDMI MacBook Port Model {i}" + " x" * 40)
        for i in range(5)
    ]
    with pytest.raises(WriterError, match="structure"):
        select_title(
            candidates,
            keywords=["usb", "hub", "adapter", "hdmi", "macbook"],
        )


def test_selector_rejects_segment_one_below_five_keyword_floor() -> None:
    candidates = [
        TitleCandidate(text=f"USB Hub - Adapter HDMI MacBook Port Model {i}" + " x" * 35)
        for i in range(5)
    ]
    with pytest.raises(WriterError, match="segment 1"):
        select_title(
            candidates,
            keywords=["usb", "hub", "adapter", "hdmi", "macbook"],
        )


def test_selector_strict_rejects_all_caps_and_known_seller() -> None:
    all_caps = [
        TitleCandidate(text=f"USB HUB ADAPTER HDMI MACBOOK - LAPTOP PORT DOCK {i}")
        for i in range(5)
    ]
    with pytest.raises(WriterError, match="policy"):
        select_title(
            all_caps,
            keywords=["usb", "hub", "adapter", "hdmi", "macbook"],
            mode=TitleMode.STRICT_AMAZON,
        )

    seller_titles = [
        TitleCandidate(text=f"Acme USB Hub Adapter HDMI MacBook - Laptop Port Dock {i}")
        for i in range(5)
    ]
    with pytest.raises(WriterError, match="policy"):
        select_title(
            seller_titles,
            keywords=["usb", "hub", "adapter", "hdmi", "macbook"],
            mode=TitleMode.STRICT_AMAZON,
            seller_name="Acme",
        )


def test_generate_strict_mock_has_five_valid_bilingual_titles(
    product: ProductInput,
    selling_points: list[SellingPoint],
) -> None:
    result = generate_titles(
        product,
        selling_points,
        llm=MockLLM("title"),
        mode=TitleMode.STRICT_AMAZON,
    )
    assert len(result.candidates) == 5
    assert all(10 <= candidate.plain_len <= 80 for candidate in result.candidates)
    assert all(candidate.text_zh for candidate in result.candidates)
    assert all(
        not validate_title(candidate.text, TitleMode.STRICT_AMAZON).errors
        for candidate in result.candidates
    )
