"""HTTP regressions for the prompt-driven creation chat."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from amazon_create.api import app
from amazon_create.config import Settings
from amazon_create.conversation.service import ConversationService
from fastapi.testclient import TestClient


@contextmanager
def _client(path: Path) -> Iterator[TestClient]:
    service = ConversationService(Settings(MOCK=True, CHECKPOINT_PATH=path))
    app.state.service = service
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            app.state.service.close()
            app.state.service = service
            yield client
    finally:
        service.close()


def test_message_stream_emits_user_snapshot_before_model_text(tmp_path: Path) -> None:
    with _client(tmp_path / "api.sqlite3") as client:
        created = client.post("/sessions").json()
        thread_id = created["state"]["thread_id"]

        response = client.post(
            f"/sessions/{thread_id}/messages",
            json={"text": "你需要哪些东西"},
        )

    assert response.status_code == 200
    body = response.text
    first_snapshot = body.index("event: snapshot")
    first_status = body.index("event: status")
    first_text = body.index("event: text")
    assert first_snapshot < first_status < first_text
    assert "你需要哪些东西" in body
    assert "我理解你的意思" in body


def test_removed_fact_action_routes_return_not_found(tmp_path: Path) -> None:
    with _client(tmp_path / "routes.sqlite3") as client:
        created = client.post("/sessions").json()
        thread_id = created["state"]["thread_id"]

        response = client.post(f"/sessions/{thread_id}/confirm")

    assert response.status_code == 404
