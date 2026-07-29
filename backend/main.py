"""Agent Manager — unified management interface for Streamlit agents."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


# ---------------------------------------------------------------------------
# WebSocket — real-time log streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws/agents/{agent_id}/logs")
async def ws_agent_logs(websocket: WebSocket, agent_id: str) -> None:
    await websocket.accept()

    # Send existing logs first
    existing = process_manager.get_logs(agent_id, tail=100)
    for line in existing:
        await websocket.send_text(line)

    # Subscribe to new logs
    queue: asyncio.Queue = process_manager.subscribe_logs(agent_id)
    try:
        while True:
            line = await queue.get()
            await websocket.send_text(line)
    except WebSocketDisconnect:
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