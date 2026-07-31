"""Agent Manager — unified management interface for packaged local agents."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from agent_registry import get_agent, list_agents
from config_service import get_config, update_config
from process_manager import AgentStatus, process_manager

app = FastAPI(title="Agent Manager", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/agents")
async def api_list_agents() -> list[dict[str, Any]]:
    return process_manager.get_all_statuses()


@app.get("/api/agents/{agent_id}")
async def api_get_agent(agent_id: str) -> dict[str, Any]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    statuses = process_manager.get_all_statuses()
    for s in statuses:
        if s["id"] == agent_id:
            return s
    return JSONResponse({"error": "Agent not found"}, status_code=404)


@app.post("/api/agents/{agent_id}/start")
async def api_start_agent(agent_id: str) -> dict[str, Any]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    try:
        info = await process_manager.start(agent_id)
        return {
            "id": agent_id,
            "status": info.status.value,
            "pid": info.pid,
            "port": info.port,
            "url": f"http://localhost:{info.port}" if info.status == AgentStatus.RUNNING else None,
            "error_message": info.error_message,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/agents/{agent_id}/stop")
async def api_stop_agent(agent_id: str) -> dict[str, Any]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    try:
        info = await process_manager.stop(agent_id)
        return {
            "id": agent_id,
            "status": info.status.value,
            "pid": info.pid,
            "error_message": info.error_message,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/agents/{agent_id}/toggle")
async def api_toggle_agent(agent_id: str) -> dict[str, Any]:
    """Atomically start or stop an agent from its reconciled host state."""
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    try:
        info = process_manager.get_status(agent_id)
        if info is None:
            return JSONResponse({"error": "Agent not found"}, status_code=404)
        process_manager.reconcile_status(agent_id)
        if info.status == AgentStatus.RUNNING:
            info = await process_manager.stop(agent_id)
        else:
            info = await process_manager.start(agent_id)
        return {
            "id": agent_id,
            "status": info.status.value,
            "pid": info.pid,
            "port": info.port,
            "url": (
                f"http://localhost:{info.port}"
                if info.status == AgentStatus.RUNNING
                else None
            ),
            "error_message": info.error_message,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/agents/{agent_id}/config")
async def api_get_config(agent_id: str) -> list[dict[str, Any]]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    return get_config(agent_id)


@app.put("/api/agents/{agent_id}/config")
async def api_update_config(agent_id: str, body: dict[str, str]) -> list[dict[str, Any]]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    try:
        return update_config(agent_id, body)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/agents/{agent_id}/logs")
async def api_get_logs(agent_id: str, lines: int = 200) -> dict[str, Any]:
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    logs = process_manager.get_logs(agent_id, tail=lines)
    return {"agent_id": agent_id, "lines": logs, "total": len(logs)}


@app.api_route(
    "/api/agents/{agent_id}/service/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def api_agent_service(agent_id: str, path: str, request: Request):
    """Proxy an active Agent API without exposing its private port to Vue."""
    agent = get_agent(agent_id)
    if agent is None:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)
    info = process_manager.reconcile_status(agent_id)
    if info is None or info.status != AgentStatus.RUNNING:
        return JSONResponse({"error": "Agent is not running"}, status_code=503)

    target = f"http://127.0.0.1:{info.port}/{path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection"}
    }

    is_stream = (
        request.method == "GET" and path.endswith("/events")
    ) or (
        agent_id == "listing-creation"
        and request.method == "POST"
        and path.startswith("sessions/")
        and path.endswith("/messages")
    )

    if is_stream:
        client = httpx.AsyncClient(timeout=None)
        upstream_request = client.build_request(
            request.method,
            target,
            params=request.query_params,
            content=body,
            headers=headers,
        )
        try:
            response = await client.send(upstream_request, stream=True)
        except Exception:
            await client.aclose()
            raise
        if response.is_error:
            content = await response.aread()
            await response.aclose()
            await client.aclose()
            return Response(
                content=content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "application/json"),
            )

        async def stream():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            stream(),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.request(
            request.method,
            target,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


# ---------------------------------------------------------------------------
# WebSocket — real-time log streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws/agents/{agent_id}/logs")
async def ws_agent_logs(websocket: WebSocket, agent_id: str) -> None:
    queue: asyncio.Queue = process_manager.subscribe_logs(agent_id)
    try:
        await websocket.accept()
        existing = process_manager.get_logs(agent_id, tail=100)
        for line in existing:
            await websocket.send_text(line)
        while True:
            line = await queue.get()
            await websocket.send_text(line)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        process_manager.unsubscribe_logs(agent_id, queue)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
