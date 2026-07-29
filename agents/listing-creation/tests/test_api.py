from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from amazon_create.api import creation_payload

if TYPE_CHECKING:
    from amazon_create.config import Settings
    from amazon_create.schemas.workflow import CreationSession


def test_creation_api_uses_live_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Settings] = []

    def fake_apply_user_message(
        session: CreationSession,
        message: str,
        *,
        settings: Settings,
    ) -> CreationSession:
        assert message == "产品: Mesh Pouch"
        captured.append(settings)
        return session

    monkeypatch.setattr("amazon_create.api.apply_user_message", fake_apply_user_message)

    creation_payload({"message": "产品: Mesh Pouch"})

    assert captured[0].mock is False


def test_creation_api_rejects_mock_override() -> None:
    with pytest.raises(ValidationError):
        creation_payload({"message": "产品: Mesh Pouch", "mock": True})
