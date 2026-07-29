"""Minimal JSON API for the React listing workbench."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationResult,
)
from amazon_copy.copy_workflow import (
    CopyWorkflow,
    CopyWorkflowState,
    next_step,
    required_inputs,
    route_for,
)
from amazon_copy.input_security import InputSecurityError, require_listing_input
from amazon_copy.simple_optimizer import run_automatic_optimization


class OptimizeRequest(BaseModel):
    """Browser request for a new or resumed optimization run."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    source_text: str = Field(min_length=1)
    context: AutomaticOptimizationContext = Field(default_factory=AutomaticOptimizationContext)


class CopyWorkflowRequest(BaseModel):
    """One serializable turn in the guided copywriting agent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    state: CopyWorkflowState
    values: dict[str, str] = Field(default_factory=dict)
    approved: bool | None = None


_WEB_ROOT = Path(__file__).with_name("web_dist")


def workflow_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and advance a guided workflow by exactly one step."""
    request = CopyWorkflowRequest.model_validate(payload)
    missing = [
        name
        for name in required_inputs(request.state)
        if not request.values.get(name, "").strip()
    ]
    if missing:
        message = f"missing required inputs: {', '.join(missing)}"
        raise ValueError(message)
    advanced = next_step(request.state, approved=request.approved)
    return _workflow_view(advanced)


def _workflow_view(state: CopyWorkflowState) -> dict[str, Any]:
    return {
        "state": state.model_dump(mode="json"),
        "route": [step.value for step in route_for(state.workflow)],
        "required_inputs": list(required_inputs(state)),
        "completed": state.step.value == "completed",
    }


def agents_payload() -> dict[str, Any]:
    """Describe all agents exposed by the management console."""
    return {
        "agents": [
            {
                "id": "safe-optimizer",
                "name": "Listing 安全优化 Agent",
                "description": "诊断现有 Listing、经确认后生成通过发布门禁的优化稿",
                "endpoint": "/api/optimize",
            },
            {
                "id": "copy-studio",
                "name": "Listing 创作 Agent",
                "description": "按撰写、五行优化、SEO 分析和文案分析四种流程逐步执行",
                "endpoint": "/api/copy-workflow",
                "workflows": [item.value for item in CopyWorkflow],
            },
        ]
    }


def optimize_payload(payload: dict[str, Any]) -> AutomaticOptimizationResult:
    """Validate one API payload and execute the existing automatic pipeline."""
    request = OptimizeRequest.model_validate(payload)
    require_listing_input(request.source_text)
    return run_automatic_optimization(request.source_text, context=request.context)


class ApiHandler(BaseHTTPRequestHandler):
    """Serve health and optimization endpoints without a web-framework dependency."""

    server_version = "AmazonCopyAPI/1.0"

    def do_OPTIONS(self) -> None:
        """Answer browser CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Return API metadata or the packaged React application."""
        if self.path == "/api/health":
            self._json_response(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/api/agents":
            self._json_response(HTTPStatus.OK, agents_payload())
            return
        self._static_response()

    def do_POST(self) -> None:
        """Run one validated optimization request."""
        if self.path not in {"/api/optimize", "/api/copy-workflow"}:
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = _object_payload(json.loads(raw))
            result: Any = (
                optimize_payload(payload)
                if self.path == "/api/optimize"
                else workflow_payload(payload)
            )
        except (
            ValidationError,
            InputSecurityError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            self._json_response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_request", "message": str(exc)},
            )
            return
        except Exception:  # noqa: BLE001
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "optimization_failed", "message": "优化服务暂时不可用"},
            )
            return
        body = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        self._json_response(HTTPStatus.OK, body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Write one concise access-log line."""
        typer.echo(f"API {self.address_string()} {format % args}")

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _static_response(self) -> None:
        requested = self.path.split("?", maxsplit=1)[0].lstrip("/") or "index.html"
        candidate = (_WEB_ROOT / requested).resolve()
        if _WEB_ROOT.resolve() not in candidate.parents or not candidate.is_file():
            candidate = _WEB_ROOT / "index.html"
        if not candidate.is_file():
            self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "frontend_not_built", "message": "Run npm run build in web/"},
            )
            return
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _object_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        message = "request body must be a JSON object"
        raise TypeError(message)
    return payload


def serve(
    host: str = typer.Option("127.0.0.1", help="API bind address."),
    port: int = typer.Option(8000, min=1, max=65535, help="API port."),
) -> None:
    """Run the React workbench API."""
    server = ThreadingHTTPServer((host, port), ApiHandler)
    typer.echo(f"Amazon Copy Console listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


app = typer.Typer(add_completion=False)
app.command()(serve)


if __name__ == "__main__":
    app()
