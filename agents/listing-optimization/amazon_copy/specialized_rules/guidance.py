"""Sanitized and size-bounded non-authoritative generation guidance."""

import re
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict

from amazon_copy.specialized_rules.models import SpecializedRuleSnapshot

MAX_GUIDANCE_BYTES: Final = 4096
_MAX_EXCERPT_BYTES: Final = 320
_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_MATCHED_HEADINGS: Final[tuple[str, ...]] = (
    "product-fact",
    "fact gate",
    "claim guardrail",
    "copy allocation",
    "copy rules",
    "title",
    "item highlights",
    "bullet",
    "variation",
    "safety",
    "compliance",
    "verification",
)


def _combine_pattern(*parts: str) -> str:
    return "".join(parts)


_INSTRUCTION_RE: Final[re.Pattern[str]] = re.compile(
    _combine_pattern(
        r"(?:ignore\s+(?:all\s+|previous\s+)?instructions|system\s+prompt|",
        r"developer\s+message|assistant\s*:|factclaim|can_authorize_facts|",
        r"priority\s*=|\bpass\b|jailbreak)",
    ),
    re.IGNORECASE,
)
_CONTROL_LINE_RE: Final[re.Pattern[str]] = re.compile(
    _combine_pattern(
        r"^\s*(?:[-*]\s*)?(?:",
        r"(?:ignore|disregard|treat|output|return|respond|write|say)\b|",
        r"(?:system|user|assistant|developer|role|instruction|prompt)\s*:|",
        r"(?:you\s+are|act\s+as|new\s+system)\b)",
    ),
    re.IGNORECASE,
)
_CONTROL_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SpecializedRuleGuidance(BaseModel):
    """One provenance-bound Markdown excerpt that cannot authorize facts."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    profile_filename: str
    content_sha256: str
    excerpt_markdown: str
    authority: Literal["internal_guidance"] = "internal_guidance"
    can_authorize_facts: Literal[False] = False


def _bounded_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore").rstrip()


def _matched_excerpt(markdown: str) -> str:
    selected: list[str] = []
    inside_match = False
    inside_fence = False
    for raw_line in markdown.splitlines():
        line = _CONTROL_RE.sub("", raw_line).strip()
        if line.startswith("```"):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        heading = _HEADING_RE.fullmatch(line)
        if heading is not None:
            title = heading.group("title").casefold()
            inside_match = any(marker in title for marker in _MATCHED_HEADINGS)
            if inside_match and not _is_instruction_line(line):
                selected.append(line)
            continue
        if inside_match and line and not _is_instruction_line(line):
            selected.append(line)
        if len("\n".join(selected).encode("utf-8")) >= _MAX_EXCERPT_BYTES:
            break
    return _bounded_utf8("\n".join(selected), _MAX_EXCERPT_BYTES)


def _is_instruction_line(line: str) -> bool:
    return _CONTROL_LINE_RE.search(line) is not None or _INSTRUCTION_RE.search(line) is not None


def guidance_from_snapshots(
    snapshots: tuple[SpecializedRuleSnapshot, ...],
) -> tuple[SpecializedRuleGuidance, ...]:
    """Extract only matched, sanitized sections within one global byte cap."""
    guidance: list[SpecializedRuleGuidance] = []
    used_bytes = 0
    for snapshot in snapshots:
        excerpt = _matched_excerpt(snapshot.content_markdown)
        remaining = MAX_GUIDANCE_BYTES - used_bytes
        if not excerpt or remaining <= 0:
            continue
        excerpt = _bounded_utf8(excerpt, remaining)
        if not excerpt:
            continue
        guidance.append(
            SpecializedRuleGuidance(
                profile_filename=snapshot.profile_filename,
                content_sha256=snapshot.content_sha256,
                excerpt_markdown=excerpt,
            )
        )
        used_bytes += len(excerpt.encode("utf-8"))
    return tuple(guidance)


__all__ = [
    "MAX_GUIDANCE_BYTES",
    "SpecializedRuleGuidance",
    "guidance_from_snapshots",
]
