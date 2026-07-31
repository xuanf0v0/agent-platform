from __future__ import annotations

import asyncio

import httpx
from fastapi import Request

import main
from process_manager import AgentStatus


def _request(method: str, path: str, body: bytes = b"") -> Request:
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


def test_optimization_messages_proxy_preserves_json_status(monkeypatch) -> None:
    info = main.process_manager.get_status("listing-optimization")
    assert info is not None
    info.status = AgentStatus.RUNNING
    monkeypatch.setattr(main.process_manager, "reconcile_status", lambda _agent_id: info)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(202, json={"run_id": "run-1"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda **_kwargs: async_client(transport=httpx.MockTransport(handler)),
    )
    response = asyncio.run(
        main.api_agent_service(
            "listing-optimization",
            "runs/run-1/messages",
            _request("POST", "/api/messages", b'{"text":"hello"}'),
        )
    )

    assert response.status_code == 202
    assert response.media_type == "application/json"
    assert response.body == b'{"run_id":"run-1"}'


def test_stream_proxy_preserves_upstream_error_status(monkeypatch) -> None:
    info = main.process_manager.get_status("listing-optimization")
    assert info is not None
    info.status = AgentStatus.RUNNING
    monkeypatch.setattr(main.process_manager, "reconcile_status", lambda _agent_id: info)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Run not found"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda **_kwargs: async_client(transport=httpx.MockTransport(handler)),
    )
    response = asyncio.run(
        main.api_agent_service(
            "listing-optimization",
            "runs/missing/events",
            _request("GET", "/api/events"),
        )
    )

    assert response.status_code == 404
    assert response.body == b'{"detail":"Run not found"}'
