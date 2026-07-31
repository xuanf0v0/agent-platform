"""HTTP boundary for the existing Listing Optimization workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock, Thread
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, TypeAdapter

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticOptimizationResult,
    CompletedOptimization,
    FailedOptimization,
    NeedsClarification,
    ProductIdentity,
)
from amazon_copy.config import Settings
from amazon_copy.final_conversation import process_final_turn
from amazon_copy.input_security import require_clarification_input, require_listing_input
from amazon_copy.run_store import OptimizationRunStore, default_run_title
from amazon_copy.simple_optimizer import run_automatic_optimization

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class StartRequest(BaseModel):
    """Input used to start an optimization run."""

    source_text: str = Field(min_length=1, max_length=64000)
    asin: str | None = None
    marketplace: str | None = None
    product_type: str | None = None


class ReplyRequest(BaseModel):
    """Clarification supplied for a paused run."""

    text: str = Field(min_length=1, max_length=16000)


class RunActionRequest(BaseModel):
    """Human action used to advance or retry a run."""

    action: Literal["approve", "retry"]


class RenameRequest(BaseModel):
    """User-supplied history title."""

    title: str = Field(min_length=1, max_length=120)


@dataclass
class RunState:
    """In-memory state and event ledger for one optimization run."""

    run_id: str
    source_text: str
    identity: ProductIdentity | None
    title: str = "新建优化"
    status: str = "queued"
    result: AutomaticOptimizationResult | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    workflow_messages: list[dict[str, Any]] = field(default_factory=list)
    chat_messages: list[dict[str, str]] = field(default_factory=list)
    turn_status: str = "idle"
    approval_token: str | None = None
    lock: RLock = field(default_factory=RLock)

    def emit(self, event: str, **payload: Any) -> None:  # noqa: ANN401
        """Append an event while holding the per-run lock."""
        with self.lock:
            self.events.append({"id": len(self.events), "event": event, **payload})

    def payload(self) -> dict[str, Any]:
        """Return the public JSON-compatible run snapshot."""
        with self.lock:
            return {
                "run_id": self.run_id,
                "source_text": self.source_text,
                "title": self.title,
                "status": self.status,
                "identity": self.identity.model_dump(mode="json") if self.identity else None,
                "result": self.result.model_dump(mode="json") if self.result else None,
                "replies": list(self.replies),
                "workflow_messages": list(self.workflow_messages),
                "chat_messages": list(self.chat_messages),
                "chat_enabled": isinstance(self.result, CompletedOptimization),
                "turn_status": self.turn_status,
                "event_cursor": len(self.events) - 1,
            }

    def durable_payload(self) -> dict[str, Any]:
        """Return state required to resume after a process restart."""
        payload = self.payload()
        payload.pop("event_cursor", None)
        payload["approval_token"] = self.approval_token
        return payload

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> RunState:
        """Rebuild runtime locks and typed models from a durable payload."""
        identity_payload = payload.get("identity")
        result_payload = payload.get("result")
        result = (
            TypeAdapter(AutomaticOptimizationResult).validate_python(result_payload)
            if isinstance(result_payload, dict)
            else None
        )
        status = str(payload.get("status") or "failed")
        turn_status = str(payload.get("turn_status") or "idle")
        chat_messages = [
            {
                "role": str(item.get("role") or "assistant"),
                "content": str(item.get("content") or ""),
            }
            for item in payload.get("chat_messages", [])
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ]
        workflow_messages = [
            dict(item)
            for item in payload.get("workflow_messages", [])
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
        ]
        if status in {"queued", "running"} or turn_status == "running":
            status = result.status if result is not None else "failed"
            turn_status = "interrupted"
            chat_messages.append(
                {
                    "role": "assistant",
                    "content": "上一次处理因服务重启中断, 请重新发送该请求。",
                }
            )
        return cls(
            run_id=str(payload["run_id"]),
            source_text=str(payload.get("source_text") or ""),
            identity=(
                ProductIdentity.model_validate(identity_payload)
                if identity_payload
                else None
            ),
            title=(
                str(payload.get("title") or "").strip()
                or default_run_title(str(payload.get("source_text") or ""))
            ),
            status=status,
            result=result,
            replies=[str(item) for item in payload.get("replies", [])],
            workflow_messages=workflow_messages,
            chat_messages=chat_messages,
            turn_status=turn_status,
            approval_token=(
                str(payload["approval_token"])
                if payload.get("approval_token") is not None
                else None
            ),
        )


app = FastAPI(title="Listing Optimization Agent API", version="1.0.0")
_runs: dict[str, RunState] = {}
_runs_lock = RLock()
_settings = Settings()
_store = OptimizationRunStore(_settings.checkpoint_path)


def _persist(run: RunState) -> None:
    now = datetime.now(UTC).isoformat()
    _store.save(
        run.run_id,
        json.dumps(run.durable_payload(), ensure_ascii=False, separators=(",", ":")),
        now,
        title=run.title,
        status=run.status,
    )


def _get_run(run_id: str) -> RunState:
    with _runs_lock:
        run = _runs.get(run_id)
        if run is None:
            payload = _store.load(run_id)
            if payload is not None:
                run = RunState.restore(payload)
                _runs[run_id] = run
                _persist(run)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _resume_context(
    run: RunState,
    *,
    mode: str,
    reply: str | None = None,
) -> AutomaticOptimizationContext:
    result = run.result
    token = getattr(result, "approval_token", None) or run.approval_token
    questions = result.questions if isinstance(result, NeedsClarification) else ()
    evidence = getattr(result, "evidence_bundle", None)
    return AutomaticOptimizationContext(
        clarification_reply=reply,
        clarification_questions=questions,
        cached_research=getattr(result, "research_cache", None),
        cached_specialized_rules=getattr(result, "specialized_rule_cache", None),
        rule_context=getattr(result, "rule_context", None),
        user_claims=evidence.user_claims if evidence else (),
        suppressed_claim_terms=evidence.suppressed_claim_terms if evidence else (),
        allowed_keywords=evidence.allowed_keywords if evidence else (),
        auto_resolve_unverified=True,
        mode=mode,
        skip_approval=False,
        approval_token=token,
        identity=run.identity,
    )


def _archive_stage(run: RunState, user_text: str) -> None:
    """Preserve the visible workflow turn before replacing the current result."""
    if run.result is None:
        return
    with run.lock:
        run.workflow_messages.extend(
            (
                {
                    "role": "assistant",
                    "status": run.result.status,
                    "result": run.result.model_dump(mode="json"),
                },
                {"role": "user", "content": user_text},
            )
        )


def _execute(run: RunState, context: AutomaticOptimizationContext) -> None:
    run.status = "running"
    run.emit("status", status="running", content="初始化模型服务")

    def progress(label: str, step: int, total: int) -> None:
        run.emit("progress", content=label, step=step, total=total)

    def quality(attempt: int, total: int, reasons: tuple[str, ...], passed: bool) -> None:
        run.emit(
            "quality",
            attempt=attempt,
            total=total,
            reasons=list(reasons),
            passed=passed,
        )

    try:
        result = run_automatic_optimization(
            run.source_text,
            context=context,
            dependencies=AutomaticOptimizationDependencies(
                progress_callback=progress,
                quality_callback=quality,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        result = FailedOptimization(code="optimization_failed", message=str(exc))
    run.result = result
    issued_token = getattr(result, "approval_token", None)
    if issued_token:
        run.approval_token = str(issued_token)
    run.status = result.status
    run.emit("result", status=result.status, result=result.model_dump(mode="json"))
    run.emit("done", status=result.status)
    _persist(run)


def _start_worker(run: RunState, context: AutomaticOptimizationContext) -> None:
    with run.lock:
        run.events.clear()
        run.status = "running"
    _persist(run)
    Thread(
        target=_execute,
        args=(run, context),
        name=f"optimization-{run.run_id[:8]}",
        daemon=True,
    ).start()


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the optimization service is available."""
    return {"status": "ok", "agent": "listing-optimization"}


@app.post("/runs", status_code=202)
def create_run(request: StartRequest) -> dict[str, Any]:
    """Create and asynchronously start an optimization run."""
    require_listing_input(request.source_text)
    identity = ProductIdentity(
        asin=request.asin,
        marketplace=request.marketplace,
        product_type=request.product_type,
    )
    if not any((identity.asin, identity.marketplace, identity.product_type)):
        identity = None
    run = RunState(
        uuid4().hex,
        request.source_text,
        identity,
        title=default_run_title(request.source_text),
    )
    with _runs_lock:
        _runs[run.run_id] = run
    _persist(run)
    context = AutomaticOptimizationContext(
        auto_resolve_unverified=True,
        mode="diagnose",
        skip_approval=False,
        identity=identity,
    )
    _start_worker(run, context)
    return run.payload()


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Return the current state of an optimization run."""
    return _get_run(run_id).payload()


@app.get("/runs")
def list_runs() -> list[dict[str, str]]:
    """List every durable optimization conversation."""
    return _store.list_summaries()


@app.patch("/runs/{run_id}")
def rename_run(run_id: str, request: RenameRequest) -> dict[str, Any]:
    """Rename one optimization conversation and preserve its full state."""
    run = _get_run(run_id)
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title must not be blank")
    run.title = title[:120]
    _persist(run)
    return run.payload()


@app.post("/runs/{run_id}/reply", status_code=202)
def reply(run_id: str, request: ReplyRequest) -> dict[str, Any]:
    """Resume a run with user clarification."""
    run = _get_run(run_id)
    if not isinstance(run.result, NeedsClarification):
        raise HTTPException(status_code=409, detail="Run is not awaiting clarification")
    require_clarification_input(request.text)
    _archive_stage(run, request.text)
    with run.lock:
        run.replies.append(request.text)
    _persist(run)
    postflight = run.result.postflight_review
    token = getattr(run.result, "approval_token", None)
    mode = "optimize" if postflight is not None or token else "diagnose"
    _start_worker(run, _resume_context(run, mode=mode, reply=request.text))
    return run.payload()


@app.post("/runs/{run_id}/actions", status_code=202)
def run_action(run_id: str, request: RunActionRequest) -> dict[str, Any]:
    """Approve an optimization result or retry its diagnosis."""
    run = _get_run(run_id)
    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is already active")
    action_text = "确认并生成上传稿" if request.action == "approve" else "重试"
    _archive_stage(run, action_text)
    mode = "optimize" if request.action == "approve" else "diagnose"
    _start_worker(run, _resume_context(run, mode=mode))
    return run.payload()


def _execute_chat(run: RunState, text: str) -> None:
    """Process one freeform completed-listing turn in a worker thread."""
    run.turn_status = "running"
    run.emit("chat_status", content="Agent 正在理解并复核终稿")
    try:
        result = run.result
        if not isinstance(result, CompletedOptimization):
            run.turn_status = "failed"
            run.emit("chat_error", message="Run is not ready for final conversation")
            return
        turn = process_final_turn(
            run.source_text,
            result,
            run.chat_messages[:-1],
            text,
            settings=_settings,
        )
        run.result = turn.result
        run.status = turn.result.status
        run.chat_messages.append({"role": "assistant", "content": turn.reply})
        run.turn_status = "idle"
        run.emit(
            "chat_result",
            content=turn.reply,
            changed=turn.changed,
            research_used=turn.research_used,
            result=turn.result.model_dump(mode="json"),
        )
    except Exception as exc:  # noqa: BLE001 -- keep last release-ready draft available
        message = str(exc) or "终稿对话处理失败, 请重试"
        run.turn_status = "failed"
        run.emit("chat_error", message=message)
    finally:
        _persist(run)
        run.emit("done", status=run.status)


@app.post("/runs/{run_id}/messages", status_code=202)
def final_message(run_id: str, request: ReplyRequest) -> dict[str, Any]:
    """Start one LLM-driven turn over a completed, release-ready listing."""
    run = _get_run(run_id)
    if not isinstance(run.result, CompletedOptimization):
        raise HTTPException(status_code=409, detail="Run has no completed listing")
    if run.turn_status == "running":
        raise HTTPException(status_code=409, detail="A conversation turn is already active")
    require_clarification_input(request.text)
    with run.lock:
        run.events.clear()
        run.chat_messages.append({"role": "user", "content": request.text})
        run.turn_status = "running"
    _persist(run)
    Thread(
        target=_execute_chat,
        args=(run, request.text),
        name=f"optimization-chat-{run.run_id[:8]}",
        daemon=True,
    ).start()
    return run.payload()


@app.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    """Delete one durable optimization conversation."""
    run = _get_run(run_id)
    if run.status == "running" or run.turn_status == "running":
        raise HTTPException(status_code=409, detail="Run is active")
    with _runs_lock:
        _runs.pop(run_id, None)
    _store.delete(run_id)


@app.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    after: Annotated[int, Query(ge=-1)] = -1,
) -> StreamingResponse:
    """Stream newly emitted run events as server-sent events."""
    run = _get_run(run_id)

    async def events() -> AsyncIterator[str]:
        cursor = after + 1
        idle = 0
        while True:
            with run.lock:
                pending = run.events[cursor:]
            if pending:
                for item in pending:
                    cursor = item["id"] + 1
                    data = json.dumps(item, ensure_ascii=False)
                    yield f"id: {item['id']}\nevent: {item['event']}\ndata: {data}\n\n"
                    if item["event"] == "done":
                        return
                idle = 0
            else:
                idle += 1
                if idle % 50 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.1)

    return StreamingResponse(events(), media_type="text/event-stream")
