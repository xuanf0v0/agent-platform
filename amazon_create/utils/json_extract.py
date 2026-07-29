"""Recover JSON from LLM output."""

from __future__ import annotations

import json
from typing import cast

JsonValue = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


class JsonExtractError(ValueError):
    """No complete JSON object/array recovered."""


def extract_json(raw: str) -> JsonValue:
    """Return the first decodable JSON object/array in *raw*."""
    if not raw.strip():
        message = "LLM response contained no JSON"
        raise JsonExtractError(message)
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            decoded = cast("JsonValue", decoder.raw_decode(raw[index:])[0])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, (dict, list)):
            return decoded
    message = "LLM response contained malformed or incomplete JSON"
    raise JsonExtractError(message)


def extract_json_object(raw: str) -> dict[str, JsonValue]:
    """Recover one JSON object."""
    value = extract_json(raw)
    if not isinstance(value, dict):
        message = "LLM JSON root must be an object"
        raise JsonExtractError(message)
    return value
