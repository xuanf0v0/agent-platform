"""HTTP API for the standalone product research agent."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from threading import Lock, Thread

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from .config import Settings
from .llm_summary import summarize
from .models import ResearchRequest, ResearchResult, ResearchRun, RunStatus
from .providers import collect_research
from .report import xlsx_bytes
from .scoring import decide, score_candidate
from .store import RunStore

app = FastAPI(title="Amazon Product Research Agent API", version="1.0.0")
settings = Settings()
store = RunStore(settings.checkpoint_path)
memory: dict[str, ResearchRun] = {}
memory_lock = Lock()


def _get(run_id: str) -> ResearchRun:
    with memory_lock:
        run = memory.get(run_id)
    if run is None:
        run = store.get(run_id)
        if run:
            with memory_lock:
                memory[run_id] = run
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return run


def _save(run: ResearchRun) -> None:
    store.save(run)
    with memory_lock:
        memory[run.run_id] = run


def _event(run: ResearchRun, name: str, **payload: object) -> None:
    run.events.append({"id": len(run.events), "event": name, **payload})
    _save(run)


def _summary(run: ResearchRun) -> list[str]:
    result = run.result
    if result is None or not result.candidates:
        return ["没有返回可识别候选，请补充更具体的品类、关键词或检查数据源配置。"]
    best = max(result.candidates, key=lambda item: item.score.overall if item.score else 0)
    score = best.score.overall if best.score else 0
    return [
        f"最高机会候选：{best.title}，综合分 {score}/100。",
        f"当前决策：{result.decision.value if result.decision else '待补充证据'}。",
        "所有市场数字应以右侧证据列表和下载的 JSON/Excel 为准。",
    ]


def _user_cost(text: str) -> float | None:
    match = re.search(
        r"(?:采购成本|成本|cost)\s*[:：=]?\s*(?:USD|US\$|\$)?\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _run_worker(run: ResearchRun, request: ResearchRequest) -> None:
    run.status = RunStatus.RUNNING
    _event(run, "status", content="正在检查数据源")
    try:

        async def execute():
            queries = request.candidate_refs or [request.prompt]
            all_candidates = []
            all_evidence = []
            all_gaps = []
            for query in queries:
                candidates, evidence, gaps = await collect_research(
                    settings,
                    mode=request.mode,
                    query=f"{request.prompt}\n候选：{query}" if request.candidate_refs else query,
                    marketplace=request.marketplace,
                )
                all_candidates.extend(candidates)
                all_evidence.extend(evidence)
                all_gaps.extend(gaps)
            unique = {}
            for candidate in all_candidates:
                unique.setdefault(candidate.asin or candidate.title.casefold(), candidate)
            return list(unique.values()), all_evidence, list(dict.fromkeys(all_gaps))

        candidates, evidence, gaps = asyncio.run(execute())
        confirmed_cost = _user_cost(request.prompt)
        if confirmed_cost is not None:
            for candidate in candidates:
                if candidate.cost_usd is None:
                    candidate.cost_usd = confirmed_cost
        _event(run, "progress", content="市场数据采集完成", step=4, total=8)
        for candidate in candidates:
            score_candidate(candidate, request.constraints)
            _event(run, "candidate", candidate=candidate.model_dump(mode="json"))
        decision = decide(candidates, request.constraints, gaps)
        result = ResearchResult(
            candidates=candidates,
            evidence=evidence,
            gaps=gaps,
            constraints=request.constraints,
            decision=decision,
        )
        deterministic_summary = _summary(
            ResearchRun(source_text=run.source_text, mode=run.mode, result=result, title=run.title)
        )
        try:
            result.executive_summary = summarize(settings, result) or deterministic_summary
        except Exception:  # noqa: BLE001 -- deterministic report remains available
            result.executive_summary = deterministic_summary
            result.gaps.append("LLM 摘要不可用，当前展示确定性摘要")
        result.report_markdown = "\n".join(
            ["# Amazon 选品研究报告", "", *[f"- {item}" for item in result.executive_summary]]
        )
        run.result = result
        missing_cost = bool(candidates and all(item.cost_usd is None for item in candidates))
        run.status = (
            RunStatus.NEEDS_CLARIFICATION if not candidates or missing_cost else RunStatus.COMPLETED
        )
        _event(run, "result", status=run.status.value, result=result.model_dump(mode="json"))
        _event(run, "done", status=run.status.value)
    except Exception as exc:  # noqa: BLE001 -- worker failures must be persisted for the UI
        run.error = str(exc) or type(exc).__name__
        run.status = RunStatus.FAILED
        _event(run, "error", message=run.error)
        _event(run, "done", status=run.status.value)
    finally:
        _save(run)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "product-research"}


@app.get("/runs")
def list_runs() -> list[dict[str, str]]:
    return store.list()


@app.post("/runs", status_code=202)
def create_run(request: ResearchRequest) -> ResearchRun:
    if request.mode == "compare" and len(request.candidate_refs) < 2:
        raise HTTPException(
            status_code=422, detail="Compare mode requires at least two candidate_refs"
        )
    run = ResearchRun(
        source_text=request.prompt,
        mode=request.mode,
        marketplace=request.marketplace,
        title=request.prompt[:48],
    )
    with memory_lock:
        memory[run.run_id] = run
    _save(run)
    Thread(
        target=_run_worker,
        args=(run, request),
        name=f"product-research-{run.run_id[:8]}",
        daemon=True,
    ).start()
    return run


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> ResearchRun:
    return _get(run_id)


@app.patch("/runs/{run_id}")
def rename_run(run_id: str, body: dict[str, str]) -> ResearchRun:
    run = _get(run_id)
    title = str(body.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title must not be blank")
    run.title = title[:120]
    _save(run)
    return run


@app.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    run = _get(run_id)
    if run.status == RunStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Run is active")
    store.delete(run_id)
    with memory_lock:
        memory.pop(run_id, None)


@app.post("/runs/{run_id}/reply", status_code=202)
def reply(run_id: str, body: dict[str, str]) -> ResearchRun:
    run = _get(run_id)
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=422, detail="Reply must not be blank")
    if run.status == RunStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Run is active")
    run.replies.append(text)
    run.source_text = f"{run.source_text}\n补充信息：{text}"
    run.events.clear()
    constraints = run.result.constraints if run.result else None
    request = ResearchRequest(
        mode=run.mode,
        prompt=run.source_text,
        marketplace=run.marketplace,
        constraints=constraints or {},
    )
    Thread(
        target=_run_worker,
        args=(run, request),
        name=f"product-research-retry-{run.run_id[:8]}",
        daemon=True,
    ).start()
    return run


@app.post("/runs/{run_id}/actions", status_code=202)
def action(run_id: str, body: dict[str, str]) -> ResearchRun:
    run = _get(run_id)
    if body.get("action") not in {"retry", "recalculate"}:
        raise HTTPException(status_code=422, detail="Supported actions are retry and recalculate")
    if run.status == RunStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Run is active")
    constraints = run.result.constraints if run.result else None
    request = ResearchRequest(
        mode=run.mode,
        prompt=run.source_text,
        marketplace=run.marketplace,
        constraints=constraints or {},
    )
    run.events.clear()
    Thread(
        target=_run_worker,
        args=(run, request),
        name=f"product-research-action-{run.run_id[:8]}",
        daemon=True,
    ).start()
    return run


@app.get("/runs/{run_id}/events")
async def events(run_id: str, after: int = Query(default=-1, ge=-1)) -> StreamingResponse:
    run = _get(run_id)

    async def stream() -> AsyncIterator[str]:
        cursor = after + 1
        idle = 0
        while True:
            pending = run.events[cursor:]
            if pending:
                for item in pending:
                    cursor = int(item["id"]) + 1
                    yield f"id: {item['id']}\nevent: {item['event']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item["event"] == "done":
                        return
                idle = 0
            else:
                idle += 1
                if idle % 50 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/runs/{run_id}/artifacts/json")
def json_artifact(run_id: str) -> Response:
    run = _get(run_id)
    return Response(
        content=run.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="product-research-{run_id}.json"'},
    )


@app.get("/runs/{run_id}/artifacts/xlsx")
def xlsx_artifact(run_id: str) -> Response:
    run = _get(run_id)
    return Response(
        content=xlsx_bytes(run),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="product-research-{run_id}.xlsx"'},
    )
