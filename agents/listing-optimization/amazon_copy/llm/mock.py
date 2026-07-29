"""Deterministic, strictly offline role fixtures."""

from __future__ import annotations

import asyncio
import json
from importlib.resources import files
from typing import Any, Final

from amazon_copy.llm.base import ConfigError


def _load(name: str) -> dict[str, Any]:
    resource = files("amazon_copy.llm").joinpath("fixtures", name)
    with resource.open(encoding="utf-8") as stream:
        return json.load(stream)


def _fixtures() -> dict[str, Any]:
    research = _load("research_pack.json")
    titles = _load("titles.json")
    strict_titles = _load("titles_strict.json")
    bullets = _load("bullets.json")
    optimized_listing = _load("optimized_listing.json")
    selling_points = [
        {"rank": rank, "text_en": text, "text_zh": zh, "rationale": "fixture"}
        for rank, (text, zh) in enumerate(
            (
                ("Seven useful ports", "七个实用接口"),
                ("4K display output", "4K 显示输出"),
                ("PD pass-through charging", "PD 直通充电"),
                ("Dual card reading", "双卡读取"),
                ("Compact travel design", "便携设计"),
            ),
            start=1,
        )
    ]
    rows = [{"item": term, "present": True} for term in bullets["keywords"]]
    dimensions = [
        {"key": key, "score": 8.0, "rationale": "offline fixture"}
        for key in (
            "compliance",
            "seo",
            "grammar",
            "readability",
            "selling_points",
            "localization",
            "professionalism",
            "emotion",
            "cta",
        )
    ]
    optimized = {
        **bullets,
        "bullets": [
            {
                **row,
                "change_rationale": "**Improved shopper intent while preserving facts**",
            }
            for row in bullets["bullets"]
        ],
    }
    return {
        "research_audience": research["audience"],
        "research_motives": research["motives"],
        "research_feedback": research["feedback"],
        "research_product": {"product_intro": research["product_intro"]},
        "research_instruction": {"instruction_decode": research["instruction_decode"]},
        "research_competitor_params": {"parameters": research["competitor"]["parameters"]},
        "research_competitor_selling": {"selling_points": research["competitor"]["selling_points"]},
        "research_competitor_copy": {"copy_notes": research["competitor"]["copy_notes"]},
        "selling_points": {"selling_points": selling_points},
        "title": titles,
        "title_strict": strict_titles,
        "bullets": bullets,
        "seo_check": {"intent_rows": [], "rootword_rows": rows, "keyword_rows": rows},
        "optimize_bp": optimized,
        "scorecard": {"dimensions": dimensions, "overall": 8.0},
        "compliance_advice_zh": {
            "summary_zh": "当前合规检查整体可接受，建议上架前再核对主观宣传用语。",
            "issues_zh": [
                "若存在主观/促销禁用词，可能触发审核风险",
            ],
            "advice_zh": [
                "删除 best seller、free shipping 等促销用语",
                "用可验证的规格与材质描述替代主观夸张词",
            ],
        },
        "score_summary_zh": {
            "overall_zh": "总分8.0，表现优秀。产品在合规性、SEO和可读性方面表现突出。",
            "strengths_zh": [
                "合规性与SEO表现出色，符合亚马逊要求",
                "可读性强，消费者容易理解产品核心卖点",
            ],
            "weaknesses_zh": [
                "号召性用语可以进一步增强以提升转化率",
            ],
            "advice_zh": [
                "在结尾增加明确的购买号召用语",
                "考虑突出更多情感化卖点以增强吸引力",
            ],
        },
        "listing_optimizer": optimized_listing,
        "product_type_classifier": {
            "product_type": "GENERAL_PRODUCT",
            "confidence": 0.4,
            "rationale": "offline fixture default; use heuristics for known titles",
        },
        "listing_diagnosis_zh": {
            "issues": [
                {
                    "level": "P0",
                    "title": "字段完整性待确认",
                    "detail_zh": "离线 fixture：请核对残句、缺失参数与未证实宣称。",
                },
                {
                    "level": "P1",
                    "title": "后台词可再去重",
                    "detail_zh": "离线 fixture：可见字段重复词根应在定稿后重算。",
                },
            ],
            "scores": [
                {
                    "dimension": key,
                    "score": 7.0,
                    "rationale_zh": f"离线 fixture · {key}",
                }
                for key in (
                    "compliance",
                    "a9_seo",
                    "semantic_coverage",
                    "grammar",
                    "readability",
                    "selling_points",
                    "localization",
                    "technical_accuracy",
                    "emotional_appeal",
                    "purchase_motivation",
                )
            ],
            "average_score": 7.0,
            "fix_order": [
                "立即修复残句与 BLOCK 项——P0。",
                "补齐卖点与后台词去重——P1。",
                "定稿可见字段后重新生成后台词。",
            ],
        },
    }


ROLES: Final[tuple[str, ...]] = (
    "research_audience",
    "research_motives",
    "research_feedback",
    "research_product",
    "research_instruction",
    "research_competitor_params",
    "research_competitor_selling",
    "research_competitor_copy",
    "selling_points",
    "title",
    "bullets",
    "seo_check",
    "optimize_bp",
    "scorecard",
    "score_summary_zh",
    "compliance_advice_zh",
    "listing_optimizer",
    "listing_diagnosis_zh",
    "product_type_classifier",
)


class MockLLM:
    """Return JSON fixtures without importing or constructing a network client."""

    def __init__(self, role: str) -> None:
        """Select one supported offline response role."""
        if role not in ROLES:
            message = f"Unknown LLM role: {role!r}. Valid roles: {list(ROLES)}"
            raise ConfigError(message)
        self._role = role
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of fixture completions requested."""
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Return the selected role fixture as JSON without network access."""
        del system, kwargs
        self._call_count += 1
        role = self._role
        if role == "title":
            try:
                requested_mode = str(json.loads(user).get("title_mode", ""))
            except (json.JSONDecodeError, AttributeError):
                requested_mode = ""
            if requested_mode.endswith("strict_amazon"):
                role = "title_strict"
        if role == "listing_optimizer":
            return json.dumps(_optimized_from_source(user), ensure_ascii=False)
        if role == "product_type_classifier":
            return json.dumps(_product_type_from_source(user), ensure_ascii=False)
        fixture = _fixtures()[role]
        return json.dumps(fixture, ensure_ascii=False)


def _product_type_from_source(user: str) -> dict[str, object]:
    """Infer a catalog product type from the offline classifier payload."""
    from amazon_copy.specialized_rules.product_types import (  # noqa: PLC0415
        infer_product_type_heuristic,
    )

    try:
        payload = json.loads(user)
        source = payload.get("source_listing") or {}
        title = str(source.get("title") or "")
        highlights = str(source.get("item_highlights") or "")
        bullets = source.get("bullets") or []
        text = " ".join(
            (
                title,
                highlights,
                *([str(item) for item in bullets] if isinstance(bullets, list) else []),
            )
        )
    except (json.JSONDecodeError, TypeError, AttributeError):
        text = user
    product_type = infer_product_type_heuristic(text) or "GENERAL_PRODUCT"
    confidence = 0.9 if product_type != "GENERAL_PRODUCT" else 0.3
    return {
        "product_type": product_type,
        "confidence": confidence,
        "rationale": "offline fixture classification",
    }


def _optimized_from_source(user: str) -> dict[str, Any]:
    """Build a deterministic optimized listing from the caller's source facts.

    Offline mock must never invent an unrelated product. Prefer rewriting the
    pasted title/bullets; fall back to the package fixture only when the user
    payload cannot be parsed.
    """
    fallback = _load("optimized_listing.json")
    try:
        payload = json.loads(user)
        source = payload["source_listing"]
        title = str(source["title"]).strip()
        bullets_raw = source["bullets"]
        if not isinstance(bullets_raw, list) or not bullets_raw:
            raise TypeError("bullets must be a non-empty list")
        bullets = [str(item).strip() for item in bullets_raw if str(item).strip()]
        if not title or not bullets:
            raise ValueError("empty source title or bullets")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return fallback

    # Light, deterministic polish: keep facts, mark as optimized for tests/UI.
    # Cap title for paste-ready path (≤75 plain chars); Studio SEO lengths live elsewhere.
    polished_title = title if title.lower().startswith("optimized:") else f"Optimized: {title}"
    if len(polished_title) > 75:
        polished_title = polished_title[:75].rstrip()
    polished_bullets: list[str] = []
    for index, bullet in enumerate(bullets, start=1):
        body = bullet
        if not body.lower().startswith("optimized"):
            body = f"Optimized point {index}: {bullet}"
        polished_bullets.append(body)
    highlights = (
        f"Key benefits refined from your {len(polished_bullets)} source points "
        f"while preserving product facts."
    )
    if len(highlights) > 125:
        highlights = highlights[:125].rstrip()
    return {
        "title": polished_title,
        "item_highlights": highlights,
        "bullets": polished_bullets,
    }


# ── Studio (async) roles ──────────────────────────────────────────

STUDIO_ROLES: Final[tuple[str, ...]] = (
    "writer_seo",
    "writer_differentiation",
    "writer_clarity",
    "critic",
    "reviser",
    "judge",
    "integrator",
)


def _studio_fixtures() -> dict[str, Any]:
    """Deterministic inline fixtures for studio (async) roles.

    Every fixture is JSON-serialisable and fully offline.  No hidden
    repair or retry logic — one call, one answer.
    """
    return {
        "writer_seo": {
            "title": "USB-C Hub 7-in-1 — 4K HDMI, PD 100W, SD/TF Card Reader for MacBook Pro/Air/Dell",
            "titles": [
                "USB-C Hub 7-in-1 — 4K HDMI, PD 100W, SD/TF Card Reader for MacBook Pro/Air/Dell",
                "7-in-1 USB-C Hub: 4K HDMI, 100W PD, SD/TF Reader for MacBook & USB-C Laptops",
                "USB C Hub Multiport Adapter 7-in-1 with 4K HDMI and 100W Charging for MacBook Dell",
            ],
            "bullets": [
                "7-in-1 USB-C Hub: Expand your laptop with HDMI 4K@30Hz, 100W PD pass-through, USB 3.0 data, SD/TF card slots, and 3.5 mm audio — all in one compact adapter",
                "4K Ultra HD Output: Stream or mirror display content at sharp 4K@30Hz via HDMI. Ideal for presentations, home office, and entertainment setups",
                "100W Power Delivery: Keep your laptop charged at full speed while using all ports. Smart PD chip protects against overcurrent and overheating",
                "High-Speed Data Transfer: Two USB 3.0 ports deliver up to 5 Gbps for instant file transfers, external drives, and peripherals",
                "Universal Compatibility: Plug-and-play with MacBook Pro/Air 2020–2024, Dell XPS, iPad Pro USB-C, ChromeBook, and Surface devices",
            ],
            "keywords": ["usb c hub", "7 in 1 hub", "hdmi adapter", "macbook hub"],
        },
        "writer_differentiation": {
            "angle": "All-in-One Productivity Hub — replaces five separate dongles",
            "titles": [
                "All-in-One Productivity Hub — replaces five separate dongles for MacBook and USB-C laptops",
                "USB-C Hub 7-in-1: One Compact Dock for HDMI, PD 100W Charging, Data & Card Reading",
                "Travel Hub 7-in-1: Consolidate HDMI, 100W PD, SD Card Reader into One Portable Unit",
            ],
            "differentiators": [
                "Unlike single-port adapters, this hub consolidates HDMI, PD charging, data, audio, and card reading into one portable unit — no swapping dongles",
                "True 100W PD pass-through keeps high-power laptops charged at full speed; many competitors cap at 60W or less",
                "Dual SD/TF slots let photographers and content creators transfer from both camera and drone cards simultaneously",
            ],
            "target_audience": "Remote workers, digital nomads, content creators, and professionals needing a single-dock travel solution.",
        },
        "writer_clarity": {
            "plain_title": "USB-C Hub, 7-in-1 Adapter with 4K HDMI and 100W Charging",
            "titles": [
                "USB-C Hub, 7-in-1 Adapter with 4K HDMI and 100W Charging",
                "7-in-1 USB-C Adapter: 4K HDMI, 100W Charging, SD Card Reader for Any USB-C Laptop",
                "USB C Hub Multiport Adapter 7-in-1 with 4K HDMI Output and 100W Power Delivery",
            ],
            "plain_bullets": [
                "Connect your laptop to a 4K monitor, charge at full speed, read SD cards, and plug in USB devices — all at once",
                "Works with MacBook, Dell, iPad Pro, and any USB-C laptop. Just plug it in — no driver needed",
                "Small enough to carry in your pocket. Replaces five separate cables and adapters",
                "Safe charging: built-in protection stops overheating and overcurrent",
            ],
        },
        "critic": {
            "verdict": "pass_with_revisions",
            "strengths": [
                "Strong SEO keyword coverage in title and opening bullet.",
                "Clear differentiation on 100W PD vs 60W competitors.",
            ],
            "issues": [
                "Bullet 3 is too technical ('PD chip protection') — reframe as shopper benefit.",
                "Missing social proof / usage scenario in final bullet.",
                "Title exceeds 200 characters in SOP SEO mode.",
            ],
            "score": 7.2,
        },
        "reviser": {
            "revision_title": "USB-C Hub 7-in-1 — 4K HDMI, 100W Charging, SD Card Reader for MacBook & USB-C Laptops",
            "revision_titles": [
                "USB-C Hub 7-in-1 — 4K HDMI, 100W Charging, SD Card Reader for MacBook & USB-C Laptops",
                "7-in-1 USB-C Hub: 4K HDMI, 100W PD, SD/TF Card Reader for MacBook Pro/Air & USB-C",
                "USB C Hub Multiport Adapter — 4K HDMI, 100W PD, SD Card Slot for Dell XPS MacBook",
            ],
            "revision_bullets": [
                "7 ports in 1 compact hub: connect 4K HDMI monitor, charge your laptop at full 100W, transfer files at 5 Gbps, and read SD/TF cards — all simultaneously",
                "True 4K@30Hz output for crisp presentations, movies, or extended desktop. No lag, no flicker",
                "Full-speed 100W Power Delivery keeps even high-performance laptops charged while using every port — no more drained batteries during workflow",
                "Instant SD/TF card access — transfer photos and video from your camera or drone without a separate reader",
                "Universal plug-and-play: works with MacBook Pro/Air, Dell XPS, iPad Pro, Surface, and Chromebook. Driver-free setup",
            ],
            "changes_applied": ["shortened title under 200 chars", "reframed PD safety as uptime benefit", "added SD/TF use case"],
        },
        "judge": {
            "winner": "revised_writer_seo",
            "rankings": [
                {"rank": 1, "candidate": "reviser", "score": 8.5, "rationale": "Best balance of SEO density, clarity, and persuasive benefits."},
                {"rank": 2, "candidate": "writer_seo", "score": 7.8, "rationale": "Strong keyword coverage but title slightly long."},
                {"rank": 3, "candidate": "writer_clarity", "score": 7.0, "rationale": "Clear and simple but lacks SEO depth."},
                {"rank": 4, "candidate": "writer_differentiation", "score": 6.5, "rationale": "Good differentiators but not a standalone listing."},
            ],
            "dimensions": {"seo": 8.0, "clarity": 8.5, "persuasion": 8.0, "compliance": 9.0},
        },
        "integrator": {
            "final_title": "USB-C Hub 7-in-1 — 4K HDMI, 100W PD, SD/TF Card Reader for MacBook & USB-C Laptops",
            "final_bullets": [
                "7-in-1 USB-C Hub: Expand your laptop with 4K HDMI@30Hz, 100W power delivery, USB 3.0 data at 5 Gbps, SD/TF card slots, and 3.5 mm audio — all in one portable adapter.",
                "True 4K Ultra HD Output: Stream or mirror to an external monitor at sharp 4K@30Hz. Perfect for presentations, home office, and cinema-quality entertainment.",
                "Full-Speed 100W Charging: Keeps even high-performance laptops charged while every port is in use. Advanced safety chip protects against overcurrent and overheating.",
                "Instant SD & TF Card Access: Transfer photos and video from your camera, drone, or phone directly — no separate reader required.",
                "Universal Plug-and-Play: Works with MacBook Pro/Air, Dell XPS, iPad Pro, Surface, and Chromebook. Driver-free setup in seconds.",
            ],
            "sources_used": ["writer_seo", "reviser"],
        },
    }


class AsyncMockLLM:
    """Return JSON fixtures without network access — async interface.

    No hidden repair or retry logic.  One ``complete()`` call returns the
    pre-built fixture for the selected studio role.
    """

    def __init__(self, role: str) -> None:
        """Select one supported offline async/studio response role."""
        if role not in STUDIO_ROLES:
            message = f"Unknown studio LLM role: {role!r}. Valid roles: {list(STUDIO_ROLES)}"
            raise ConfigError(message)
        self._role = role
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return the number of fixture completions requested."""
        return self._call_count

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Return the selected studio role fixture as JSON (async, no network)."""
        del system, user, kwargs
        self._call_count += 1
        fixture = _studio_fixtures()[self._role]
        return json.dumps(fixture, ensure_ascii=False)
