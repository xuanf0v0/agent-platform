"""Runtime selection of packaged Amazon policy and category guidance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from amazon_create.schemas.brief import ProductBrief

_RESOURCE_ROOT: Final[Path] = Path(__file__).with_name("resources")
_POLICY_ROOT: Final[Path] = _RESOURCE_ROOT / "amazon-listing-policy-and-semantic-copy"
_COPY_ROOT: Final[Path] = _RESOURCE_ROOT / "amazon-cosmo-rufus-copywriting"

_CORE_RULES: Final[tuple[Path, ...]] = (
    _RESOURCE_ROOT / "amazon-listing-creation" / "SKILL.md",
    _POLICY_ROOT / "SKILL.md",
    _POLICY_ROOT / "references" / "amazon-policy-baseline-2026.md",
    _POLICY_ROOT / "references" / "cosmo-alexa-shopping-boundaries.md",
    _POLICY_ROOT / "references" / "source-material-reconciliation.md",
    _COPY_ROOT / "SKILL.md",
)

_CATEGORY_RULES: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("plastic folder", "pocket folder", "school folder"), "office-supplies-folders.md"),
    (("folder competitor", "folder asin"), "office-supplies-folder-competitor-research.md"),
    (
        (
            "desktop file organizer",
            "vertical file organizer",
            "paper tray organizer",
            "printer stand",
            "monitor riser",
            "desk organizer",
        ),
        "desktop-file-organizers-and-office-supplies.md",
    ),
    (("mesh zipper pouch", "document bag", "puzzle storage pouch"), "mesh-zipper-pouches.md"),
    (("wall file organizer", "magnetic file holder", "hanging wall file"), "wall-file-organizers.md"),
    (("squishy toy", "party favor", "goodie bag", "classroom prize"), "kids-party-favors-squishy-toys.md"),
    (
        ("polycarbonate greenhouse", "greenhouse panel", "twin-wall panel", "greenhouse sheet"),
        "polycarbonate-greenhouse-panels.md",
    ),
    (
        ("greenhouse sheet", "greenhouse panel", "greenhouse replacement panel", "clear roof panel"),
        "greenhouse-polycarbonate-panels.md",
    ),
    (
        ("long handle scrub brush", "long handle floor scrub brush", "deck brush", "3-in-1 scrub brush"),
        "long-handle-floor-scrub-brushes.md",
    ),
    (("floor scrub brush", "shower scrubber", "grout brush"), "floor-scrub-brushes.md"),
)


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Selected packaged documents and prompt-safe content."""

    files: tuple[str, ...]
    content: str
    category_files: tuple[str, ...]


def _brief_haystack(brief: ProductBrief) -> str:
    return " ".join(
        (
            brief.product_name,
            brief.product_type,
            brief.specs_text,
            brief.notes,
        )
    ).casefold()


def selected_rule_paths(brief: ProductBrief, *, include_image: bool = False) -> tuple[Path, ...]:
    """Select core rules plus every category reference matching the brief."""
    paths = list(_CORE_RULES)
    haystack = _brief_haystack(brief)
    selected_names: set[str] = set()
    for triggers, filename in _CATEGORY_RULES:
        if any(trigger in haystack for trigger in triggers):
            selected_names.add(filename)
    for filename in sorted(selected_names):
        paths.append(_COPY_ROOT / "references" / filename)
    if include_image:
        paths.append(_COPY_ROOT / "references" / "amazon-image-design.md")
    return tuple(paths)


def load_rule_context(brief: ProductBrief, *, include_image: bool = False) -> RuleContext:
    """Load selected packaged rules without silently ignoring missing files."""
    paths = selected_rule_paths(brief, include_image=include_image)
    sections: list[str] = []
    files: list[str] = []
    category_files: list[str] = []
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"required packaged rule missing: {path}")
        relative = str(path.relative_to(_RESOURCE_ROOT))
        files.append(relative)
        if path.parent.name == "references" and path.parent.parent == _COPY_ROOT:
            category_files.append(relative)
        sections.append(f"\n--- RULE SOURCE: {relative} ---\n{path.read_text(encoding='utf-8')}")
    return RuleContext(
        files=tuple(files),
        content="\n".join(sections),
        category_files=tuple(category_files),
    )


def category_rule_names(brief: ProductBrief) -> tuple[str, ...]:
    """Return selected category filenames for UI and tests."""
    return tuple(Path(name).name for name in load_rule_context(brief).category_files)


__all__ = ["RuleContext", "category_rule_names", "load_rule_context", "selected_rule_paths"]
