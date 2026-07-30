"""HTTP boundary for the existing Listing Optimization workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from threading import RLock, Thread
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticOptimizationResult,
    FailedOptimization,
    NeedsClarification,
    ProductIdentity,
)
from amazon_copy.input_security import require_clarification_input, require_listing_input
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


@dataclass
class RunState:
    """In-memory state and event ledger for one optimization run."""

    run_id: str
    source_text: str
    identity: ProductIdentity | None
    status: str = "queued"
    result: AutomaticOptimizationResult | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
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
                "status": self.status,
                "identity": self.identity.model_dump(mode="json") if self.identity else None,
                "result": self.result.model_dump(mode="json") if self.result else None,
                "replies": list(self.replies),
                "event_cursor": len(self.events) - 1,
            }


app = FastAPI(title="Listing Optimization Agent API", version="1.0.0")
_runs: dict[str, RunState] = {}
_runs_lock = RLock()


def _get_run(run_id: str) -> RunState:
    with _runs_lock:
        run = _runs.get(run_id)
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


def _start_worker(run: RunState, context: AutomaticOptimizationContext) -> None:
    with run.lock:
        run.events.clear()
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
    run = RunState(uuid4().hex, request.source_text, identity)
    with _runs_lock:
        _runs[run.run_id] = run
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


@app.post("/runs/{run_id}/reply", status_code=202)
def reply(run_id: str, request: ReplyRequest) -> dict[str, Any]:
    """Resume a run with user clarification."""
    run = _get_run(run_id)
    if not isinstance(run.result, NeedsClarification):
        raise HTTPException(status_code=409, detail="Run is not awaiting clarification")
    require_clarification_input(request.text)
    run.replies.append(request.text)
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
    mode = "optimize" if request.action == "approve" else "diagnose"
    _start_worker(run, _resume_context(run, mode=mode))
    return run.payload()


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
