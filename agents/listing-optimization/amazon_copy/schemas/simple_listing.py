"""Typed boundary for the simplified listing optimization workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Final, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from amazon_copy.input_security import (
    MAX_LISTING_INPUT_BYTES as _MAX_LISTING_INPUT_BYTES,
)
from amazon_copy.input_security import (
    InputSecurityError,
    require_listing_fields,
    require_listing_input,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MAX_LISTING_INPUT_BYTES: Final[int] = _MAX_LISTING_INPUT_BYTES

TitleLabelPosition = Literal["same_line", "own_line", "none"]
HighlightsLabelPosition = Literal["same_line", "own_line"]
BulletMarker = Literal["·", "•", "-", "*", "number_dot", "number_paren", "plain"]


class ListingFormatTemplate(BaseModel):
    """Typed source layout captured for copy-ready rendering."""

    model_config = ConfigDict(frozen=True)

    title_label: str | None = None
    title_label_position: TitleLabelPosition = "none"
    item_highlights_label: str | None = None
    item_highlights_position: HighlightsLabelPosition = "own_line"
    section_label: str | None = None
    bullet_marker: BulletMarker = "plain"
    blank_line_after_title: bool = False
    blank_line_after_highlights: bool = False
    blank_line_after_section: bool = False
    blank_line_between_points: bool = False
    terminal_punctuation: str | None = None


class SourceListingCopy(BaseModel):
    """One source title and one to ten source copy points."""

    model_config = ConfigDict(frozen=True)

    title: NonBlankText
    item_highlights: str = ""
    bullets: list[NonBlankText] = Field(min_length=1, max_length=10)
    backend_search_terms: str = ""
    format_template: ListingFormatTemplate = Field(default_factory=ListingFormatTemplate)


class OptimizedListingCopy(BaseModel):
    """The complete paste-ready result shown by the simplified UI."""

    model_config = ConfigDict(frozen=True)

    title: NonBlankText
    item_highlights: NonBlankText
    bullets: list[NonBlankText] = Field(min_length=1, max_length=10)
    backend_search_terms: str = ""


@dataclass(frozen=True, slots=True)
class CopyPointsParseError(ValueError):
    """Raised when pasted source copy cannot become one to ten points."""

    reason: str

    def __str__(self) -> str:
        """Return the user-facing parser failure reason."""
        return self.reason


_POINT_MARKER: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<marker>[·•*\-]|\d+[.)])\s*(?P<text>.+?)\s*$"
)
_TITLE_LABEL: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<label>(?:标题|title)\s*[:\uFF1A])\s*(?P<text>.*?)\s*$", re.IGNORECASE
)
_SECTION_LABELS: Final[frozenset[str]] = frozenset({"五点", "五点描述", "bullet points", "bullets"})
_HIGHLIGHTS_LABEL: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<label>(?:item highlights|highlights)\s*[:\uFF1A]?)\s*(?P<text>.*?)\s*$",
    re.IGNORECASE,
)
_BACKEND_SEARCH_LABEL: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<label>(?:backend\s*search\s*terms?|search\s*terms?|后台词|后台搜索词)"
    r"\s*[:\uFF1A])\s*(?P<text>.*?)\s*$",
    re.IGNORECASE,
)
# Optional verified-facts lines embedded in the same paste box as the listing.
_FACT_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:"
    r"事实|已确认事实|已确认产品事实|"
    r"verified\s*facts?|product\s*facts?|facts?"
    r")\s*[:\uFF1A]\s*(?P<body>.*?)\s*$",
    re.IGNORECASE,
)
_TERMINAL_PUNCTUATION: Final[frozenset[str]] = frozenset("\u3002.!\uff01?\uff1f\uff1b;\uff0c,")
_MAX_COPY_POINTS: Final[int] = 10
_EMPTY_COPY_MESSAGE: Final[str] = "请至少粘贴一条优化前文案要点。"
_TOO_MANY_COPY_MESSAGE: Final[str] = "一次最多支持 10 条文案要点。"
_MISSING_TITLE_MESSAGE: Final[str] = "请粘贴包含标题和文案要点的完整 Listing。"
_INPUT_TOO_LARGE_MESSAGE: Final[str] = "Listing 输入过长, 请缩短后重试。"


def _require_safe_listing_input(raw: str) -> None:
    try:
        require_listing_input(raw)
    except InputSecurityError as error:
        raise CopyPointsParseError(_INPUT_TOO_LARGE_MESSAGE) from error


def split_verified_facts_from_listing(raw: str) -> tuple[str, str | None]:
    """Split optional fact marker lines out of a single pasted listing block.

    Recognizes lines like ``事实: …`` / ``Verified facts: …``. When the label
    has an empty body, subsequent non-empty lines are absorbed until a blank
    line or another fact label. Remaining text is the listing to optimize;
    joined fact bodies become ``verified_facts`` (or ``None`` when absent).
    """
    _require_safe_listing_input(raw)
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    listing_lines: list[str] = []
    fact_parts: list[str] = []
    index = 0
    while index < len(lines):
        match = _FACT_LINE.fullmatch(lines[index])
        if match is None:
            listing_lines.append(lines[index])
            index += 1
            continue
        body = (match.group("body") or "").strip()
        if body:
            fact_parts.append(body)
            index += 1
            continue
        index += 1
        chunk: list[str] = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped:
                index += 1
                break
            if _FACT_LINE.fullmatch(lines[index]) is not None:
                break
            chunk.append(stripped)
            index += 1
        if chunk:
            fact_parts.append(" ".join(chunk))
    listing = "\n".join(listing_lines).strip()
    facts = "; ".join(fact_parts).strip() or None
    return listing, facts


def parse_copy_points(raw: str) -> list[str]:
    """Parse a pasted list or paragraph block into one to ten copy points."""
    _require_safe_listing_input(raw)
    lines = raw.splitlines()
    marked = [_POINT_MARKER.match(line) for line in lines]
    if any(match is not None for match in marked):
        points: list[str] = []
        for line, match in zip(lines, marked, strict=True):
            stripped = line.strip()
            if not stripped:
                continue
            if match is not None:
                points.append(match.group("text").strip())
            elif points:
                points[-1] = f"{points[-1]} {stripped}"
    elif any(not line.strip() for line in lines):
        points = [" ".join(paragraph.split()) for paragraph in re.split(r"\n\s*\n", raw)]
        points = [point for point in points if point]
    else:
        points = [line.strip() for line in lines if line.strip()]
    if not points:
        raise CopyPointsParseError(_EMPTY_COPY_MESSAGE)
    if len(points) > _MAX_COPY_POINTS:
        raise CopyPointsParseError(_TOO_MANY_COPY_MESSAGE)
    try:
        require_listing_fields(title="safe", item_highlights="", points=points)
    except InputSecurityError as error:
        raise CopyPointsParseError(_INPUT_TOO_LARGE_MESSAGE) from error
    return points


def parse_listing_block(  # noqa: C901, PLR0912, PLR0915
    raw: str,
) -> SourceListingCopy:
    """Parse one pasted listing and capture its recognizable source layout."""
    _require_safe_listing_input(raw)
    if not raw.strip():
        raise CopyPointsParseError(_EMPTY_COPY_MESSAGE)
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = next((position for position, line in enumerate(lines) if line.strip()), len(lines))
    if _POINT_MARKER.match(lines[index]) is not None:
        raise CopyPointsParseError(_MISSING_TITLE_MESSAGE)
    title_label: str | None = None
    title_position: TitleLabelPosition = "none"
    title_match = _TITLE_LABEL.fullmatch(lines[index])
    if title_match is not None:
        title_label = title_match.group("label").strip()
        title = title_match.group("text").strip()
        index += 1
        title_position = "same_line" if title else "own_line"
        if not title:
            while index < len(lines) and not lines[index].strip():
                index += 1
            if index == len(lines):
                raise CopyPointsParseError(_EMPTY_COPY_MESSAGE)
            title = lines[index].strip()
            index += 1
    else:
        title = lines[index].strip()
        index += 1
    blank_after_title = index < len(lines) and not lines[index].strip()
    while index < len(lines) and not lines[index].strip():
        index += 1

    item_label: str | None = None
    item_highlights = ""
    item_position: HighlightsLabelPosition = "own_line"
    item_match = _HIGHLIGHTS_LABEL.fullmatch(lines[index]) if index < len(lines) else None
    if item_match is not None:
        item_label = item_match.group("label").strip()
        item_highlights = item_match.group("text").strip()
        item_position = "same_line" if item_highlights else "own_line"
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if item_position == "own_line" and not item_highlights and index < len(lines):
            # Own-line label: capture following highlight body. Prefer multi-line
            # bodies until the first bullet marker; otherwise take the next line
            # when more listing content remains (plain bullets without markers).
            has_markers_ahead = any(
                _POINT_MARKER.match(line) for line in lines[index:] if line.strip()
            )
            if has_markers_ahead:
                highlight_lines: list[str] = []
                while (
                    index < len(lines)
                    and lines[index].strip()
                    and _POINT_MARKER.match(lines[index]) is None
                ):
                    if lines[index].strip().rstrip(":\uff1a").casefold() in _SECTION_LABELS:
                        break
                    highlight_lines.append(lines[index].strip())
                    index += 1
                item_highlights = " ".join(highlight_lines)
            else:
                candidate = lines[index].strip()
                if (
                    candidate
                    and candidate.rstrip(":\uff1a").casefold() not in _SECTION_LABELS
                    and _BACKEND_SEARCH_LABEL.fullmatch(lines[index]) is None
                    and any(line.strip() for line in lines[index + 1 :])
                ):
                    item_highlights = candidate
                    index += 1
                    while index < len(lines) and not lines[index].strip():
                        index += 1

    section_label: str | None = None
    if index < len(lines) and lines[index].strip().rstrip(":\uff1a").casefold() in _SECTION_LABELS:
        section_label = lines[index].strip()
        index += 1
    blank_after_section = (
        index < len(lines) and not lines[index].strip() if section_label else False
    )
    while index < len(lines) and not lines[index].strip():
        index += 1

    point_lines = lines[index:]
    backend_search_terms = ""
    trimmed_point_lines: list[str] = []
    for line in point_lines:
        backend_match = _BACKEND_SEARCH_LABEL.fullmatch(line)
        if backend_match is not None:
            backend_search_terms = backend_match.group("text").strip()
            continue
        trimmed_point_lines.append(line)
    point_lines = trimmed_point_lines
    matches = [_POINT_MARKER.match(line) for line in point_lines if line.strip()]
    has_markers = any(match is not None for match in matches)
    marker_style: BulletMarker = "plain"
    points: list[str] = []
    blank_between = False
    if has_markers:
        first_match = next(match for match in matches if match is not None)
        marker = first_match.group("marker")
        if marker == "·":
            marker_style = "·"
        elif marker == "•":
            marker_style = "•"
        elif marker == "-":
            marker_style = "-"
        elif marker == "*":
            marker_style = "*"
        elif marker.endswith("."):
            marker_style = "number_dot"
        else:
            marker_style = "number_paren"
        for line in point_lines:
            if not line.strip():
                blank_between = blank_between or bool(points)
                continue
            match = _POINT_MARKER.match(line)
            if match is not None:
                points.append(match.group("text").strip())
            elif points:
                points[-1] = f"{points[-1]} {line.strip()}"
            else:
                points.append(line.strip())
    else:
        points = [line.strip() for line in point_lines if line.strip()]
        blank_between = any(not line.strip() for line in point_lines) and len(points) > 1
    # Drop a trailing plain backend-search line if label was on its own line.
    if points and not backend_search_terms:
        trailing = _BACKEND_SEARCH_LABEL.fullmatch(points[-1])
        if trailing is not None:
            backend_search_terms = trailing.group("text").strip()
            points = points[:-1]
    if not points:
        raise CopyPointsParseError(_EMPTY_COPY_MESSAGE)
    if len(points) > _MAX_COPY_POINTS:
        raise CopyPointsParseError(_TOO_MANY_COPY_MESSAGE)
    try:
        require_listing_fields(
            title=title,
            item_highlights=item_highlights,
            points=points,
        )
    except InputSecurityError as error:
        raise CopyPointsParseError(_INPUT_TOO_LARGE_MESSAGE) from error
    endings = [point[-1] for point in points if point and point[-1] in _TERMINAL_PUNCTUATION]
    terminal = endings[0] if endings and all(ending == endings[0] for ending in endings) else None
    template = ListingFormatTemplate(
        title_label=title_label,
        title_label_position=title_position,
        item_highlights_label=item_label,
        item_highlights_position=item_position,
        section_label=section_label,
        bullet_marker=marker_style,
        blank_line_after_title=blank_after_title,
        blank_line_after_section=blank_after_section,
        blank_line_between_points=blank_between,
        terminal_punctuation=terminal,
    )
    return SourceListingCopy(
        title=title,
        item_highlights=item_highlights,
        bullets=points,
        backend_search_terms=backend_search_terms,
        format_template=template,
    )


def _marker_prefix(style: BulletMarker, index: int) -> str:
    match style:
        case "·" | "•" | "-" | "*":
            return f"{style} "
        case "number_dot":
            return f"{index}. "
        case "number_paren":
            return f"{index}) "
        case "plain":
            return ""
        case unreachable:
            assert_never(unreachable)


def format_optimized_listing(  # noqa: C901, PLR0912
    result: OptimizedListingCopy,
    template: ListingFormatTemplate,
) -> str:
    """Render the optimized fields as one editable block in source layout."""
    lines: list[str] = []
    match template.title_label_position:
        case "same_line":
            label = template.title_label or ""
            lines.append(
                f"{label}{result.title}"
                if label.endswith((":", "\uff1a"))
                else f"{label} {result.title}"
            )
        case "own_line":
            lines.extend((template.title_label or "", result.title))
        case "none":
            lines.append(result.title)
        case unreachable:
            assert_never(unreachable)
    if template.blank_line_after_title:
        lines.append("")
    if result.item_highlights:
        item_label = template.item_highlights_label or "Item Highlights:"
        match template.item_highlights_position:
            case "same_line":
                lines.append(
                    f"{item_label}{result.item_highlights}"
                    if item_label.endswith((":", "\uff1a"))
                    else f"{item_label} {result.item_highlights}"
                )
            case "own_line":
                lines.extend((item_label, result.item_highlights))
            case unreachable:
                assert_never(unreachable)
        if template.blank_line_after_highlights:
            lines.append("")
    if template.section_label:
        lines.append(template.section_label)
        if template.blank_line_after_section:
            lines.append("")
    for index, bullet in enumerate(result.bullets, start=1):
        if index > 1 and template.blank_line_between_points:
            lines.append("")
        punctuation = template.terminal_punctuation
        text = (
            f"{bullet}{punctuation}"
            if punctuation and bullet[-1] not in _TERMINAL_PUNCTUATION
            else bullet
        )
        lines.append(f"{_marker_prefix(template.bullet_marker, index)}{text}")
    if result.backend_search_terms.strip():
        lines.extend(("", f"Backend Search Terms: {result.backend_search_terms.strip()}"))
    return "\n".join(lines).strip()


def format_canonical_optimized_listing(result: OptimizedListingCopy) -> str:
    """Render the fixed upload-review shape used by the automatic workbench."""
    lines = ["Title", result.title, "Item Highlights", result.item_highlights]
    for index, bullet in enumerate(result.bullets, start=1):
        lines.extend((f"Bullet Point {index}", bullet))
    lines.extend(("Backend Search Terms", result.backend_search_terms.strip()))
    return "\n".join(lines).strip()
