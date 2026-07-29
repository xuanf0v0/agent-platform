"""Load the immutable prompt assets shipped with amazon-copy-agent."""

from __future__ import annotations

import re
from importlib.resources import files

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def load_prompt(name: str) -> str:
    """Return a constitution or agent prompt by stem.

    Names are deliberately restricted to simple stems so product text can never
    turn this helper into a path traversal primitive.
    """
    if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
        message = "prompt name must be a lowercase identifier"
        raise ValueError(message)
    relative_path = "constitution.md" if name == "constitution" else f"agents/{name}.md"
    resource = files("amazon_copy.prompts").joinpath(relative_path)
    try:
        content = resource.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        message = f"Prompt file not found: {name}"
        raise FileNotFoundError(message) from None
    if not content:
        message = f"Prompt file is empty: {name}"
        raise ValueError(message)
    return content
