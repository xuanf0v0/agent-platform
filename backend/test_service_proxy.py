from __future__ import annotations

from pathlib import Path

import httpx
from agent_harness import api as harness_api
from agent_harness.api import create_app
from agent_harness.models import AgentState, AgentStatus
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


class StaticStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aiter__(self):
        yield self.content


def _running_status() -> AgentStatus:
    return AgentStatus(
        id="listing-optimization",
        name="Listing Optimization",
        description="test",
        icon="",
        port=8502,
        status=AgentState.RUNNING,
        pid=1,
    )


def test_optimization_messages_proxy_preserves_json_status(tmp_path, monkeypatch) -> None:
    app = create_app(ROOT / "harness-agents", state_path=tmp_path / "state.db")
    monkeypatch.setattr(app.state.supervisor, "status", lambda _agent_id: _running_status())

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            202,
            headers={"content-type": "application/json"},
            stream=StaticStream(b'{"run_id":"run-1"}'),
        )

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        harness_api.httpx,
        "AsyncClient",
        lambda **_kwargs: async_client(transport=httpx.MockTransport(handler)),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/agents/listing-optimization/service/runs/run-1/messages",
            json={"text": "hello"},
        )

    assert response.status_code == 202
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"run_id": "run-1"}


def test_stream_proxy_preserves_upstream_error_status(tmp_path, monkeypatch) -> None:
    app = create_app(ROOT / "harness-agents", state_path=tmp_path / "state.db")
    monkeypatch.setattr(app.state.supervisor, "status", lambda _agent_id: _running_status())

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            headers={"content-type": "application/json"},
            stream=StaticStream(b'{"detail":"Run not found"}'),
        )

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        harness_api.httpx,
        "AsyncClient",
        lambda **_kwargs: async_client(transport=httpx.MockTransport(handler)),
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/agents/listing-optimization/service/runs/missing/events"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}
