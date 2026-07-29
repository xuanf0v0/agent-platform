"""Clamp, lint, and evidence-authorize final creation deliverable."""

from __future__ import annotations

from amazon_create.compliance.lint_bridge import lint_deliverable
from amazon_create.compliance.paste_ready import clamp_paste_ready_lengths
from amazon_create.schemas.deliverable import BulletDeliverable, CreationDeliverable
from amazon_create.schemas.evidence import (
    ClaimAuthorizationResult,
    FactRow,
    authorize_copy_claims,
)
from amazon_create.utils.text_metrics import plain_len, strip_md_bold


def _coerce_text(value: object) -> str:
    """Coerce a raw LLM field to clean text, joining lists with ', '."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value or "")


def finalize_deliverable(
    raw: dict[str, object],
    *,
    brand: str = "",
    media_category: bool = False,
    fact_ledger: tuple[FactRow, ...] | list[FactRow] = (),
) -> tuple[CreationDeliverable, ClaimAuthorizationResult]:
    """Build deliverable with length clamp, claim auth, and lint."""
    title = strip_md_bold(_coerce_text(raw.get("title"))).strip()
    highlights = strip_md_bold(_coerce_text(raw.get("item_highlights"))).strip()
    highlights_zh = _coerce_text(raw.get("item_highlights_zh"))
    title, highlights = clamp_paste_ready_lengths(title, highlights)

    bullets_raw = raw.get("bullets") or []
    bullets: list[BulletDeliverable] = []
    if isinstance(bullets_raw, list):
        for item in bullets_raw[:5]:
            if isinstance(item, dict):
                text = strip_md_bold(str(item.get("text") or "")).strip()
                text_zh = str(item.get("text_zh") or "").strip()
            else:
                text = strip_md_bold(str(item)).strip()
                text_zh = ""
            if text:
                bullets.append(BulletDeliverable(text=text, text_zh=text_zh))

    while len(bullets) < 5:
        bullets.append(
            BulletDeliverable(
                text="待补 - Add a verified buyer decision with product evidence",
                text_zh="待补 - 补充有证据的购买决策信息",
            )
        )

    search_terms = str(raw.get("search_terms") or "").strip().lower()
    encoded = search_terms.encode("utf-8")
    if len(encoded) > 250:
        search_terms = encoded[:250].decode("utf-8", errors="ignore").rstrip()

    unresolved = raw.get("unresolved") or []
    unresolved_t = tuple(str(x) for x in unresolved) if isinstance(unresolved, list) else ()

    auth = authorize_copy_claims(
        title=title,
        item_highlights=highlights,
        bullets=[b.text for b in bullets],
        ledger=fact_ledger,
    )
    unresolved_merged = tuple(dict.fromkeys([*unresolved_t, *auth.unresolved]))

    draft = CreationDeliverable(
        title=title or "Product Title 待补",
        title_zh=_coerce_text(raw.get("title_zh")),
        title_chars=plain_len(title),
        item_highlights=highlights or "Key verified product details 待补",
        item_highlights_zh=highlights_zh,
        item_highlights_chars=plain_len(highlights),
        bullets=bullets[:5],
        search_terms=search_terms,
        search_terms_bytes=len(search_terms.encode("utf-8")),
        unresolved=unresolved_merged,
        notes_zh=str(raw.get("notes_zh") or ""),
    )

    lint = lint_deliverable(
        draft,
        brand=brand,
        media_category=media_category,
    )
    status = str(lint.get("status") or "PASS")
    if status not in {"PASS", "WARN", "BLOCK"}:
        status = "WARN"
    issues: list[str] = []
    for bucket in ("errors", "warnings"):
        for row in lint.get(bucket) or []:
            if isinstance(row, dict):
                issues.append(f"{row.get('field')}: {row.get('message')}")
    for claim in auth.blocked_claims:
        issues.append(f"evidence:{claim}")
        status = "BLOCK"
    for warn in auth.warnings:
        issues.append(f"evidence_warn:{warn}")
        if status == "PASS":
            status = "WARN"

    stats = lint.get("stats") or {}
    deliverable = draft.model_copy(
        update={
            "title_chars": int(stats.get("title_characters") or draft.title_chars),
            "item_highlights_chars": int(
                stats.get("item_highlights_characters") or draft.item_highlights_chars
            ),
            "search_terms_bytes": int(
                stats.get("search_terms_utf8_bytes") or draft.search_terms_bytes
            ),
            "policy_status": status,
            "policy_issues": tuple(issues[:30]),
        }
    )
    return deliverable, auth
