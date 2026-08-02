"""HTTP boundary for the conversational Listing Creation Agent."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from amazon_create.config import Settings
from amazon_create.conversation.service import ConversationService


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=64000)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AsinRequest(BaseModel):
    asin: str = Field(default="", max_length=10)


def _payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(_payload(data), ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = ConversationService(Settings())
    app.state.service = service
    yield
    service.close()


app = FastAPI(title="Listing Creation Agent API", version="1.0.0", lifespan=lifespan)


def _service() -> ConversationService:
    return app.state.service


def _snapshot(thread_id: str):
    try:
        return _service().snapshot(thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "listing-creation"}


@app.get("/sessions")
def sessions() -> list[dict[str, str]]:
    return _service().list_sessions()


@app.post("/sessions")
def create_session() -> Any:
    return _payload(_service().create_session())


@app.get("/sessions/{thread_id}")
def get_session(thread_id: str) -> Any:
    return _payload(_snapshot(thread_id))


@app.patch("/sessions/{thread_id}")
def rename_session(thread_id: str, request: RenameRequest) -> Any:
    _snapshot(thread_id)
    return _payload(_service().rename_session(thread_id, request.title))


@app.patch("/sessions/{thread_id}/asin")
def set_asin(thread_id: str, request: AsinRequest) -> Any:
    _snapshot(thread_id)
    return _payload(_service().set_asin(thread_id, request.asin))


@app.delete("/sessions/{thread_id}", status_code=204)
def delete_session(thread_id: str) -> None:
    _snapshot(thread_id)
    _service().delete_session(thread_id)


@app.post("/sessions/{thread_id}/messages")
def send_message(thread_id: str, request: MessageRequest) -> StreamingResponse:
    _snapshot(thread_id)
    _service().enqueue_message(thread_id, request.text)

    def events() -> Iterator[str]:
        yield _sse("snapshot", _service().snapshot(thread_id))
        try:
            for event in _service().stream_pending_turn(thread_id):
                yield _sse(event.kind, {"content": event.content})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})
        else:
            yield _sse("snapshot", _service().snapshot(thread_id))

    return StreamingResponse(events(), media_type="text/event-stream")
