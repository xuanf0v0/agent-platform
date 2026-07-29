"""JSON API and packaged React host for the listing creation agent."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amazon_create.config import Settings
from amazon_create.pipeline.creation_pipeline import apply_user_message, new_session
from amazon_create.schemas.workflow import CreationSession

_WEB_ROOT = Path(__file__).with_name("web_dist")


class CreationTurnRequest(BaseModel):
    """One browser turn with optional prior session state."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    session: CreationSession | None = None


def creation_payload(payload: dict[str, Any]) -> CreationSession:
    """Validate and execute one creation-agent turn."""
    request = CreationTurnRequest.model_validate(payload)
    session = request.session or new_session()
    return apply_user_message(session, request.message, settings=Settings(MOCK=False))


class ApiHandler(BaseHTTPRequestHandler):
    """Serve creation turns and the production React application."""

    server_version = "AmazonCreateAPI/1.0"

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json_response(HTTPStatus.OK, {"status": "ok", "agent": "listing-creation"})
            return
        self._static_response()

    def do_POST(self) -> None:
        if self.path != "/api/session/turn":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                message = "request body must be a JSON object"
                raise TypeError(message)
            result = creation_payload(payload)
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json_response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "invalid_request", "message": str(exc)},
            )
            return
        except Exception:  # noqa: BLE001
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "creation_failed", "message": "创作服务暂时不可用"},
            )
            return
        self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8100, min=1, max=65535),
) -> None:
    """Run the packaged listing creation application."""
    server = ThreadingHTTPServer((host, port), ApiHandler)
    typer.echo(f"Amazon Creation Agent listening on http://{host}:{port}")
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
