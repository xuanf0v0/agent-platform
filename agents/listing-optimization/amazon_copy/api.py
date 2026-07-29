"""JSON API and packaged React host for Listing Optimization."""

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
from amazon_copy.automatic_research import secure_research_cache
from amazon_copy.input_security import InputSecurityError, require_listing_input
from amazon_copy.simple_optimizer import run_automatic_optimization

_WEB_ROOT = Path(__file__).with_name("web_dist")


class OptimizeRequest(BaseModel):
    """One React workbench request for a new or resumed optimization run."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    source_text: str = Field(min_length=1)
    context: AutomaticOptimizationContext = Field(default_factory=AutomaticOptimizationContext)


def optimize_payload(payload: dict[str, Any]) -> AutomaticOptimizationResult:
    """Validate one request and execute the existing optimization control plane."""
    request = OptimizeRequest.model_validate(payload)
    require_listing_input(request.source_text)
    result = run_automatic_optimization(request.source_text, context=request.context)
    return _secure_result_cache(result)


def _secure_result_cache(result: AutomaticOptimizationResult) -> AutomaticOptimizationResult:
    """Keep browser-visible research cache redacted as in the former UI."""
    if result.research_cache is None:
        return result
    research_cache = secure_research_cache(result.research_cache)
    updates: dict[str, object] = {"research_cache": research_cache}
    if result.evidence_bundle is not None:
        updates["evidence_bundle"] = result.evidence_bundle.model_copy(
            update={"research": research_cache.bundle}
        )
    return result.model_copy(update=updates)


class ApiHandler(BaseHTTPRequestHandler):
    """Serve the optimization API and built React application."""

    server_version = "AmazonCopyAPI/2.0"

    def do_OPTIONS(self) -> None:
        """Answer local-development browser CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Return health metadata or the production React application."""
        if self.path == "/api/health":
            self._json_response(HTTPStatus.OK, {"status": "ok", "agent": "listing-optimization"})
            return
        self._static_response()

    def do_POST(self) -> None:
        """Run a validated optimization request."""
        if self.path != "/api/optimize":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = _object_payload(json.loads(self.rfile.read(content_length)))
            result = optimize_payload(payload)
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
        self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Write concise API access logs."""
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
    port: int = typer.Option(8502, min=1, max=65535, help="API port."),
) -> None:
    """Run the React Listing Optimization workbench."""
    server = ThreadingHTTPServer((host, port), ApiHandler)
    typer.echo(f"Listing Optimization listening on http://{host}:{port}")
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
