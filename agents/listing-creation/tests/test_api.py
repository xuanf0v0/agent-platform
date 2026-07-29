from __future__ import annotations

from amazon_create.api import creation_payload


def test_creation_api_starts_and_resumes_session() -> None:
    first = creation_payload({"message": "产品: Mesh Pouch\n站点: US\n规格: A4", "mock": True})
    assert first.brief.is_ready
    second = creation_payload(
        {"message": "认可", "session": first.model_dump(mode="json"), "mock": True}
    )
    assert second.revision == 1
    assert second.stage.value == "audience"
