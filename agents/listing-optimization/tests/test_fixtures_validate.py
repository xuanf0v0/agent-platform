import json
from pathlib import Path

import pytest
from amazon_copy.compliance.check import validate_bullets, validate_title
from amazon_copy.schemas import BulletPoint, ResearchPack, TitleCandidate, TitleMode
from amazon_copy.utils.text_metrics import meets_kw_rw_floors
from pydantic import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_research_fixture_validates_without_llm() -> None:
    assert ResearchPack.model_validate(load("research_pack.json")).audience.segments


def test_all_five_titles_are_valid_and_clean() -> None:
    titles = load("titles.json")["titles"]
    assert len(titles) == 5
    for raw in titles:
        candidate = TitleCandidate.model_validate(raw)
        assert 100 <= candidate.plain_len <= 200
        assert validate_title(candidate.text, TitleMode.SOP_SEO).errors == []


def test_bullets_validate_and_meet_aggregate_density_floors() -> None:
    raw = load("bullets.json")
    bullets = [BulletPoint.model_validate(item) for item in raw["bullets"]]
    texts = [bp.text for bp in bullets]
    assert validate_bullets(texts, "write").errors == []
    ok, detail = meets_kw_rw_floors(texts, raw["keywords"], raw["rootwords"])
    assert ok, detail
    assert detail["kw_count"] >= 10
    assert detail["rw_count"] >= 20


def test_intentionally_broken_fixture_is_rejected() -> None:
    broken = {"text": "too short.", "text_zh": "无效"}
    with pytest.raises(ValidationError):
        BulletPoint.model_validate(broken)


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(json.JSONDecodeError):
        json.loads('{"bullets": [')
