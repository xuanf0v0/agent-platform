"""Recover a JSON value from strict, fenced, or lightly wrapped LLM output."""

from __future__ import annotations

import json
from typing import cast

JsonValue = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


class JsonExtractError(ValueError):
    """Raised when no complete JSON object or array can be recovered."""


def extract_json(raw: str) -> JsonValue:
    """Return the first decodable JSON object/array in *raw*.

    Scanning with ``JSONDecoder.raw_decode`` avoids brittle brace slicing and
    accepts the common ``Here is the result: {...}`` and fenced-JSON shapes.
    """
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
    """Recover one JSON object, rejecting arrays and scalar values."""
    value = extract_json(raw)
    if not isinstance(value, dict):
        message = "LLM JSON root must be an object"
        raise JsonExtractError(message)
    return value


def extract_json_array(raw: str) -> list[JsonValue]:
    """Recover one JSON array, rejecting objects and scalar values."""
    value = extract_json(raw)
    if not isinstance(value, list):
        message = "LLM JSON root must be an array"
        raise JsonExtractError(message)
    return value
