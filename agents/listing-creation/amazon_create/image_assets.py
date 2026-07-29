"""Bounded in-memory image assets for the local creation-agent API."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from threading import Lock
from typing import Final
from uuid import uuid4

_ALLOWED_MIME_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_BYTES: Final = 6 * 1024 * 1024
_MAX_SESSION_BYTES: Final = 24 * 1024 * 1024
_MAX_IMAGES: Final = 8
_MAX_SESSIONS: Final = 32
_DATA_URL_RE: Final = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\r\n]+)$"
)


@dataclass(frozen=True, slots=True)
class StoredImage:
    """One validated browser upload retained only in server memory."""

    asset_id: str
    name: str
    mime_type: str
    data_url: str
    size_bytes: int


_LOCK = Lock()
_SESSION_IMAGES: dict[str, tuple[StoredImage, ...]] = {}


def register_images(session_id: str, images: list[dict[str, str]]) -> tuple[StoredImage, ...]:
    """Validate and replace uploaded images for one local session."""
    if not session_id.strip():
        raise ValueError("session_id is required")
    if not images or len(images) > _MAX_IMAGES:
        raise ValueError(f"upload between 1 and {_MAX_IMAGES} images")
    stored: list[StoredImage] = []
    total = 0
    for row in images:
        name = str(row.get("name") or "image").strip()[:120]
        data_url = str(row.get("data_url") or "").strip()
        match = _DATA_URL_RE.fullmatch(data_url)
        if match is None:
            raise ValueError("only JPEG, PNG, or WebP data URLs are supported")
        mime_type = match.group(1)
        if mime_type not in _ALLOWED_MIME_TYPES:
            raise ValueError(f"unsupported image type: {mime_type}")
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid base64 image") from exc
        if not raw or len(raw) > _MAX_IMAGE_BYTES:
            raise ValueError("each image must be between 1 byte and 6 MB")
        total += len(raw)
        if total > _MAX_SESSION_BYTES:
            raise ValueError("combined image upload exceeds 24 MB")
        stored.append(
            StoredImage(
                asset_id=uuid4().hex,
                name=name,
                mime_type=mime_type,
                data_url=data_url,
                size_bytes=len(raw),
            )
        )
    result = tuple(stored)
    with _LOCK:
        if session_id not in _SESSION_IMAGES and len(_SESSION_IMAGES) >= _MAX_SESSIONS:
            _SESSION_IMAGES.pop(next(iter(_SESSION_IMAGES)))
        _SESSION_IMAGES[session_id] = result
    return result


def images_for_session(session_id: str) -> tuple[StoredImage, ...]:
    """Return validated images for one session."""
    with _LOCK:
        return _SESSION_IMAGES.get(session_id, ())


def clear_session_images(session_id: str) -> None:
    """Release uploaded images when a session is replaced."""
    with _LOCK:
        _SESSION_IMAGES.pop(session_id, None)


__all__ = ["StoredImage", "clear_session_images", "images_for_session", "register_images"]
