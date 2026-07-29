"""Image upload boundary tests."""

from __future__ import annotations

import base64

import pytest

from amazon_create.image_assets import clear_session_images, images_for_session, register_images


def _data_url(payload: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


def test_register_images_is_session_scoped() -> None:
    images = register_images(
        "session-a",
        [{"name": "product.png", "data_url": _data_url(b"png-bytes")}],
    )
    assert len(images) == 1
    assert images_for_session("session-a")[0].name == "product.png"
    assert images_for_session("session-b") == ()
    clear_session_images("session-a")
    assert images_for_session("session-a") == ()


def test_register_images_rejects_non_image_data() -> None:
    with pytest.raises(ValueError, match="JPEG, PNG, or WebP"):
        register_images(
            "session-b",
            [{"name": "notes.txt", "data_url": _data_url(b"text", "text/plain")}],
        )
