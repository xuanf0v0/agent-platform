"""Central limits and credential sanitization for untrusted MCP data."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import JsonValue, TypeAdapter, ValidationError

REDACTED: Final = "[REDACTED]"
PAYLOAD_OMITTED: Final = "[REMOTE PAYLOAD OMITTED]"
MAX_MCP_PAYLOAD_BYTES: Final = 64_000
MAX_MCP_PAYLOAD_ITEMS: Final = 256
MAX_MCP_PAYLOAD_DEPTH: Final = 8
MAX_MCP_CACHE_BYTES: Final = 128_000
MAX_MCP_CACHE_SNAPSHOTS: Final = 4
MAX_MCP_CACHE_CALLS: Final = 4
MAX_MCP_RESEARCH_ITEMS: Final = 96
MAX_MCP_RESEARCH_GAPS: Final = 32

PayloadLimitCode: TypeAlias = Literal[
    "payload_too_large",
    "payload_too_deep",
]

_PAYLOAD_TOO_LARGE: Final[PayloadLimitCode] = "payload_too_large"
_PAYLOAD_TOO_DEEP: Final[PayloadLimitCode] = "payload_too_deep"
_JSON_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)
_KEY_SEPARATORS_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
_CREDENTIAL_HEADERS: Final = (
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
)
_CREDENTIAL_KEY_PATTERN: Final = (
    r"[a-z0-9_.-]*(?:token|secret|password)|api[_-]?key|secret[_-]?key|key"
)
_HEADER_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?im)(?P<label>\b(?:{'|'.join(_CREDENTIAL_HEADERS)})\b\s*[:=]\s*)[^\r\n]+"
)
_ASSIGNED_CREDENTIAL_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?i)(?P<label>(?:[?&]|\b)(?:{_CREDENTIAL_KEY_PATTERN})\s*[:=]\s*)[^&#,\s\"']+"
)
_AUTH_SCHEME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:bearer|basic)\s+[^,;\s\"']+|\bdigest\s+[^\r\n]+"
)
_STANDALONE_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<![a-z0-9_-])sk-[a-z0-9_-]+(?![a-z0-9_-])"
)
_SECRET_SENTINEL_RE: Final[re.Pattern[str]] = re.compile(r"(?i)secret_sentinel")
_PEM_PRIVATE_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?is)-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----"
)
_URL_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bhttps?://[^\s<>\"']+")
_URL_USERINFO_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^/@\s]+@"
)


@dataclass(frozen=True, slots=True)
class SanitizedPayload:
    """A recursively sanitized JSON value or an explicit payload limit."""

    value: JsonValue | None
    limit_code: PayloadLimitCode | None = None


class _PayloadLimitError(Exception):
    code: PayloadLimitCode

    def __init__(self, code: PayloadLimitCode) -> None:
        self.code = code
        super().__init__(code)


class _PayloadSanitizer:
    __slots__: tuple[str, ...] = ("_byte_count", "_item_count", "_secrets")
    _secrets: tuple[str, ...]
    _item_count: int
    _byte_count: int

    def __init__(self, secrets: tuple[str, ...]) -> None:
        self._secrets = secrets
        self._item_count = 0
        self._byte_count = 0

    def sanitize(self, item: JsonValue, depth: int = 0) -> JsonValue:
        self._consume_item(depth)
        match item:
            case None | bool() | int():
                return item
            case float() as number:
                return number if math.isfinite(number) else str(number)
            case str() as text:
                self._consume_text(text)
                return sanitize_mcp_text(text, self._secrets)
            case list() as values:
                return [self.sanitize(child, depth + 1) for child in values]
            case dict() as mapping:
                return self._sanitize_mapping(mapping, depth)

    def _consume_item(self, depth: int) -> None:
        if depth > MAX_MCP_PAYLOAD_DEPTH:
            raise _PayloadLimitError(_PAYLOAD_TOO_DEEP)
        self._item_count += 1
        if self._item_count > MAX_MCP_PAYLOAD_ITEMS:
            raise _PayloadLimitError(_PAYLOAD_TOO_LARGE)

    def _consume_text(self, text: str) -> None:
        self._byte_count += len(text.encode("utf-8"))
        if self._byte_count > MAX_MCP_PAYLOAD_BYTES:
            raise _PayloadLimitError(_PAYLOAD_TOO_LARGE)

    def _sanitize_mapping(
        self,
        mapping: dict[str, JsonValue],
        depth: int,
    ) -> dict[str, JsonValue]:
        sanitized: dict[str, JsonValue] = {}
        for key, child in mapping.items():
            self._consume_text(key)
            sanitized[key] = self.sanitize(child, depth + 1)
            if is_secret_key(key):
                sanitized[key] = REDACTED
        return sanitized


def is_secret_key(key: str) -> bool:
    """Return whether a header or query key carries credential material."""
    compact = _KEY_SEPARATORS_RE.sub("", key.casefold())
    return compact in {
        "authorization",
        "proxyauthorization",
        "cookie",
        "setcookie",
        "xapikey",
        "apikey",
        "key",
        "secretkey",
    } or compact.endswith(("token", "secret", "password"))


def sanitize_mcp_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Fully redact known values and credential-shaped fields from MCP text."""
    redacted = _sanitize_credential_patterns(text, secrets)
    return _URL_RE.sub(lambda match: sanitize_mcp_url(match.group(0)), redacted)


def _sanitize_credential_patterns(text: str, secrets: tuple[str, ...] = ()) -> str:
    redacted = text
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTED)
    redacted = _HEADER_VALUE_RE.sub(rf"\g<label>{REDACTED}", redacted)
    redacted = _ASSIGNED_CREDENTIAL_RE.sub(rf"\g<label>{REDACTED}", redacted)
    redacted = _AUTH_SCHEME_RE.sub(REDACTED, redacted)
    redacted = _PEM_PRIVATE_KEY_RE.sub(REDACTED, redacted)
    redacted = _SECRET_SENTINEL_RE.sub(REDACTED, redacted)
    return _STANDALONE_SECRET_RE.sub(REDACTED, redacted)


def sanitize_mcp_url(url: str) -> str:
    """Strip URL userinfo and redact credential-bearing query values."""
    without_userinfo = _URL_USERINFO_RE.sub(r"\g<scheme>", url)
    try:
        parts = urlsplit(without_userinfo)
        hostname = parts.hostname
        port = parts.port
        if hostname is None:
            return _sanitize_credential_patterns(without_userinfo)
        query = [
            (key, REDACTED if is_secret_key(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    except ValueError:
        return _sanitize_credential_patterns(without_userinfo)
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    rebuilt = urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            urlencode(query, safe="[]"),
            parts.fragment,
        )
    )
    return _sanitize_credential_patterns(rebuilt)


def sanitize_mcp_session_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Redact credentials and remove every URL from browser/session diagnostics."""
    return _URL_RE.sub("[REDACTED URL]", sanitize_mcp_text(text, secrets))


def sanitize_mcp_payload(
    value: object,
    secrets: tuple[str, ...] = (),
) -> SanitizedPayload:
    """Recursively sanitize JSON-like MCP data while enforcing boundary limits."""
    try:
        parsed = _JSON_ADAPTER.validate_python(value)
    except ValidationError:
        parsed = sanitize_mcp_text(str(value), secrets)

    try:
        return SanitizedPayload(value=_PayloadSanitizer(secrets).sanitize(parsed))
    except _PayloadLimitError as exc:
        return SanitizedPayload(value=None, limit_code=exc.code)


def sanitize_mcp_json(
    text: str,
    secrets: tuple[str, ...] = (),
) -> SanitizedPayload | None:
    """Parse, recursively sanitize, and bound one remote JSON payload."""
    if len(text.encode("utf-8")) > MAX_MCP_PAYLOAD_BYTES:
        return SanitizedPayload(value=None, limit_code="payload_too_large")
    try:
        parsed = _JSON_ADAPTER.validate_json(text)
    except ValidationError:
        return None
    return sanitize_mcp_payload(parsed, secrets)


def sanitize_mcp_value(
    value: object,
    secrets: tuple[str, ...] = (),
) -> JsonValue:
    """Return a render-safe recursive value, omitting excessive payloads."""
    result = sanitize_mcp_payload(value, secrets)
    return PAYLOAD_OMITTED if result.value is None else result.value


__all__ = [
    "MAX_MCP_CACHE_BYTES",
    "MAX_MCP_CACHE_CALLS",
    "MAX_MCP_CACHE_SNAPSHOTS",
    "MAX_MCP_PAYLOAD_BYTES",
    "MAX_MCP_PAYLOAD_DEPTH",
    "MAX_MCP_PAYLOAD_ITEMS",
    "MAX_MCP_RESEARCH_GAPS",
    "MAX_MCP_RESEARCH_ITEMS",
    "PAYLOAD_OMITTED",
    "REDACTED",
    "PayloadLimitCode",
    "SanitizedPayload",
    "is_secret_key",
    "sanitize_mcp_json",
    "sanitize_mcp_payload",
    "sanitize_mcp_session_text",
    "sanitize_mcp_text",
    "sanitize_mcp_url",
    "sanitize_mcp_value",
]
