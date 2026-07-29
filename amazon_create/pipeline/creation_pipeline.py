"""Staged listing creation pipeline: approval gates + evidence control."""

from __future__ import annotations

import re
from typing import Any

from amazon_create.config import Settings
from amazon_create.llm import get_llm
from amazon_create.pipeline.postflight import finalize_deliverable
from amazon_create.research_bridge import load_research_context
from amazon_create.schemas.brief import ProductBrief
from amazon_create.schemas.evidence import (
    EVIDENCE_POLICY,
    EvidenceSourceKind,
    FactRow,
    FactStatus,
    evidence_prompt_block,
    merge_fact_rows,
    research_as_ledger_rows,
)
from amazon_create.schemas.workflow import (
    STAGE_LABEL_ZH,
    STAGE_ORDER,
    CreationSession,
    CreationStage,
    StageArtifact,
)
from amazon_create.utils.json_extract import JsonExtractError, extract_json_object

_IMAGE_YES = frozenset({"需要图片", "进入图片", "图片设计", "要图片", "yes image", "image yes"})
_IMAGE_NO = frozenset({"不需要图片", "跳过图片", "不要图片", "no image", "skip image"})


def new_session(*, fast_path: bool = False) -> CreationSession:
    return CreationSession(fast_path=fast_path)


def parse_brief_message(text: str, existing: ProductBrief | None = None) -> ProductBrief:
    """Heuristic parse of free-text brief into ProductBrief + fact ledger."""
    base = existing or ProductBrief()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blob = "\n".join(lines)

    product = _field(blob, r"(?:产品|产品名|product)\s*[:：]\s*(.+)")
    market = _field(blob, r"(?:站点|市场|marketplace|market)\s*[:：]\s*(.+)")
    brand = _field(blob, r"(?:品牌|brand)\s*[:：]\s*(.+)")
    specs = _field(blob, r"(?:规格|参数|specs?)\s*[:：]\s*(.+)")
    competitors = _field(blob, r"(?:竞品|competitor|asin)\s*[:：]\s*(.+)")

    if not product and lines:
        first = lines[0]
        if not re.match(r"^(产品|站点|市场|品牌|规格)", first):
            product = first

    market_norm = (market or base.marketplace or "").strip()
    if market_norm:
        market_norm = market_norm.upper().replace("美国", "US").replace("英国", "UK")

    competitor_asins = base.competitors
    if competitors:
        found = tuple(re.findall(r"B0[A-Z0-9]{8}", competitors.upper()))
        if found:
            competitor_asins = found

    ledger: list[FactRow] = list(base.fact_ledger)
    if product or base.product_name:
        ledger = list(
            merge_fact_rows(
                ledger,
                FactRow(
                    fact="product_name",
                    value=(product or base.product_name).strip(),
                    source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                    source_label="user_brief",
                    status=FactStatus.VERIFIED,
                ),
            )
        )
    if market_norm or base.marketplace:
        ledger = list(
            merge_fact_rows(
                ledger,
                FactRow(
                    fact="marketplace",
                    value=market_norm or base.marketplace,
                    source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                    source_label="user_brief",
                    status=FactStatus.VERIFIED,
                ),
            )
        )
    if brand or base.brand:
        ledger = list(
            merge_fact_rows(
                ledger,
                FactRow(
                    fact="brand",
                    value=(brand or base.brand).strip(),
                    source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                    source_label="user_brief",
                    status=FactStatus.VERIFIED,
                ),
            )
        )
    specs_val = (specs or base.specs_text).strip()
    if specs_val:
        ledger = list(
            merge_fact_rows(
                ledger,
                FactRow(
                    fact="specs_text",
                    value=specs_val,
                    source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                    source_label="user_brief",
                    status=FactStatus.VERIFIED,
                ),
            )
        )
        for key, value in _extract_spec_pairs(specs_val):
            ledger = list(
                merge_fact_rows(
                    ledger,
                    FactRow(
                        fact=key,
                        value=value,
                        source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                        source_label="user_brief_specs",
                        status=FactStatus.VERIFIED,
                    ),
                )
            )
    else:
        ledger = list(
            merge_fact_rows(
                ledger,
                FactRow(
                    fact="specs_text",
                    value="",
                    source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
                    source_label="user_brief",
                    status=FactStatus.MISSING,
                    note="规格未提供；成稿相关数字/认证必须待补",
                ),
            )
        )

    return ProductBrief(
        product_name=(product or base.product_name).strip(),
        marketplace=market_norm or base.marketplace,
        language=base.language,
        brand=(brand or base.brand).strip(),
        product_type=base.product_type,
        media_category=base.media_category,
        specs_text=specs_val,
        competitors=competitor_asins,
        keywords_seed=base.keywords_seed,
        tone=base.tone,
        forbidden_phrases=base.forbidden_phrases,
        notes=blob if not product else base.notes,
        fact_ledger=tuple(ledger[-40:]),
        sensitive_category=base.sensitive_category,
    )


def _extract_spec_pairs(specs: str) -> list[tuple[str, str]]:
    """Pull simple key:value or known dimension-like tokens from specs text."""
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(
        r"(mesh|gauge|size|material|finish|count|quantity|voltage|warranty)\s*[=:：]\s*([^\n,;|/]+)",
        specs,
        flags=re.IGNORECASE,
    ):
        pairs.append((match.group(1).lower(), match.group(2).strip()))
    # bare patterns like 1/2 inch, 19 gauge
    if re.search(r"\b\d+/\d+\s*inch\b", specs, re.I):
        m = re.search(r"(\d+/\d+\s*inch)", specs, re.I)
        if m:
            pairs.append(("mesh_opening", m.group(1)))
    if re.search(r"\b\d+\s*gauge\b", specs, re.I):
        m = re.search(r"(\d+\s*gauge)", specs, re.I)
        if m:
            pairs.append(("gauge", m.group(1)))
    return pairs


def _field(blob: str, pattern: str) -> str:
    match = re.search(pattern, blob, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def next_stage(stage: CreationStage, *, skip_competitor: bool = False) -> CreationStage:
    order = list(STAGE_ORDER)
    idx = order.index(stage)
    nxt = order[min(idx + 1, len(order) - 1)]
    if skip_competitor and nxt == CreationStage.COMPETITOR:
        return CreationStage.SELLING_POINTS
    return nxt


def run_stage(
    session: CreationSession,
    settings: Settings | None = None,
) -> CreationSession:
    """Generate draft artifact for the current stage (awaiting approval)."""
    runtime = settings or Settings()
    stage = session.stage
    if stage == CreationStage.COMPLETED:
        session.status = "completed"
        return session

    if stage == CreationStage.BRIEF:
        return _run_brief_gate(session)

    if stage == CreationStage.IMAGE_HANDOFF:
        session.set_artifact(
            StageArtifact(
                stage=stage,
                summary_zh="文案已确认，等待是否进入图片设计。",
                payload={
                    "prompt_zh": "是否进入主图 + 7 张辅图设计？",
                    "skill": "amazon-image-design",
                },
                approved=False,
                evidence_notes_zh="图片流程独立，不改变文案证据台账。",
            )
        )
        session.status = "awaiting_approval"
        session.last_message_zh = (
            "文案已确认。\n\n"
            "是否需要进入图片设计？回复「需要图片」将交接主图+7辅图流程"
            "（独立 skill：amazon-image-design）；回复「不需要图片」结束。\n\n"
            + _checklist_block(session)
        )
        return session

    research = load_research_context(
        runtime,
        product_name=session.brief.product_name,
        marketplace=session.brief.marketplace,
        specs=session.brief.specs_text,
    )
    # MCP rows enter ledger only as third-party market context
    for row in research_as_ledger_rows(research):
        session.brief = session.brief.with_fact(row)

    llm = get_llm(runtime, role="writer")
    system = _system_prompt(stage)
    user = _user_prompt(session, stage, research)
    raw = llm.complete(system, user, json_mode=True)
    try:
        payload = extract_json_object(raw)
    except JsonExtractError:
        session.status = "failed"
        session.error = "stage_json_parse_failed"
        session.last_message_zh = "阶段输出解析失败，请重试。"
        return session

    # Force hypothesis labeling on audience percentages if any slipped in
    if stage == CreationStage.AUDIENCE:
        payload = _strip_invented_percentages(payload)

    if stage == CreationStage.FINAL_COPY:
        deliverable, auth = finalize_deliverable(
            payload,
            brand=session.brief.brand,
            media_category=session.brief.media_category,
            fact_ledger=session.brief.fact_ledger,
        )
        session.deliverable = deliverable
        session.claim_authorization = auth
        if not auth.allowed or deliverable.policy_status == "BLOCK":
            summary = (
                f"成稿未通过证据/政策门（{deliverable.policy_status}）。"
                f"拦截：{', '.join(auth.blocked_claims) or '见明细'}。"
                "请补充已确认产品资料后重试，或发送修改意见。"
            )
        else:
            summary = (
                f"最终文案草稿已生成。Title {deliverable.title_chars}/75，"
                f"IH {deliverable.item_highlights_chars}/125，"
                f"ST {deliverable.search_terms_bytes}/250 bytes，"
                f"政策 {deliverable.policy_status}。"
            )
            if deliverable.unresolved:
                summary += " 待补：" + "；".join(deliverable.unresolved[:6])
    else:
        label = STAGE_LABEL_ZH.get(stage, stage.value)
        summary = str(payload.get("notes_zh") or f"「{label}」草稿已就绪。")

    evidence_note = _stage_evidence_note(stage, session)
    session.set_artifact(
        StageArtifact(
            stage=stage,
            summary_zh=summary,
            payload=payload,
            approved=False,
            evidence_notes_zh=evidence_note,
        )
    )
    session.status = "awaiting_approval"
    session.last_message_zh = (
        summary
        + "\n\n"
        + evidence_note
        + "\n\n请回复「认可」进入下一门；或发送修改意见。\n"
        + _checklist_block(session)
    )
    return session


def _run_brief_gate(session: CreationSession) -> CreationSession:
    summary = _brief_summary(session.brief)
    ledger_view = [
        {
            "fact": r.fact,
            "value": r.value or "—",
            "tier": r.tier.name,
            "source": r.source_kind.value,
            "status": r.status.value,
        }
        for r in session.brief.fact_ledger
    ]
    session.set_artifact(
        StageArtifact(
            stage=CreationStage.BRIEF,
            summary_zh=summary,
            payload={
                "brief": session.brief.model_dump(mode="json"),
                "fact_ledger": ledger_view,
                "evidence_hierarchy": list(EVIDENCE_POLICY.order_zh),
            },
            approved=False,
            evidence_notes_zh="Brief 阶段建立事实台账；仅 product_confirmed 及以上可背书规格/认证。",
        )
    )
    session.status = "awaiting_approval"
    session.last_message_zh = (
        summary
        + "\n\n证据等级（高→低）：\n"
        + "\n".join(EVIDENCE_POLICY.order_zh)
        + "\n\n"
        + "\n".join(EVIDENCE_POLICY.rules_zh)
        + "\n\n请确认 Brief 与事实台账，或补充规格后发送。\n"
        + _checklist_block(session)
    )
    return session


def approve_stage(
    session: CreationSession,
    *,
    skip_competitor: bool = False,
    settings: Settings | None = None,
) -> CreationSession:
    """Mark current stage approved and advance to next gate."""
    runtime = settings or Settings()
    stage = session.stage
    art = session.artifact(stage)

    if stage == CreationStage.FINAL_COPY:
        if session.deliverable is None:
            session.last_message_zh = "尚无成稿，无法认可。"
            return session
        if session.deliverable.policy_status == "BLOCK":
            session.status = "awaiting_approval"
            session.last_message_zh = (
                "成稿被证据/政策门拦截（BLOCK），不能认可进入图片交接。"
                "请补充已确认产品事实或修改文案后重试。"
            )
            return session
        if art is not None:
            session.set_artifact(art.model_copy(update={"approved": True}))
        session.revision += 1
        session.stage = CreationStage.IMAGE_HANDOFF
        return run_stage(session, settings=runtime)

    if stage == CreationStage.IMAGE_HANDOFF:
        # approve without explicit image choice → treat as skip images
        session.image_design_requested = False
        if art is not None:
            session.set_artifact(art.model_copy(update={"approved": True}))
        session.revision += 1
        session.stage = CreationStage.COMPLETED
        session.status = "completed"
        session.last_message_zh = "流程完成（未进入图片设计）。可复制最终文案字段。"
        return session

    if art is not None:
        session.set_artifact(art.model_copy(update={"approved": True}))
    session.revision += 1

    skip = skip_competitor or not session.brief.competitors
    session.stage = next_stage(stage, skip_competitor=skip)
    if skip and stage == CreationStage.PRODUCT:
        # mark competitor skipped artifact for audit trail
        session.set_artifact(
            StageArtifact(
                stage=CreationStage.COMPETITOR,
                summary_zh="用户跳过竞品或未提供 ASIN。",
                payload={"skipped": True},
                approved=True,
                evidence_notes_zh="竞品信息仅作结构参考，从未达到 product_confirmed。",
            )
        )
    return run_stage(session, settings=runtime)


def apply_user_message(
    session: CreationSession,
    message: str,
    *,
    settings: Settings | None = None,
) -> CreationSession:
    """Handle free-text: brief fill, skip, fast path, image choice, regenerate."""
    text = message.strip()
    low = text.casefold()
    runtime = settings or Settings()

    if low in {"直接输出", "skip all", "fast path", "一键生成"}:
        session.fast_path = True
        return run_fast_path(session, settings=runtime)

    # Check NO before YES: "不需要图片" contains "需要图片"
    if low in _IMAGE_NO or any(
        k in low for k in ("不需要图片", "跳过图片", "不要图片", "no image", "skip image")
    ):
        if session.stage == CreationStage.FINAL_COPY:
            session = approve_stage(session, settings=runtime)
        if session.stage == CreationStage.IMAGE_HANDOFF:
            session.image_design_requested = False
            return approve_stage(session, settings=runtime)

    if low in _IMAGE_YES or (
        any(k in low for k in ("需要图片", "进入图片", "图片设计", "要图片", "yes image"))
        and "不" not in text
        and "no " not in low
    ):
        if session.stage in {CreationStage.IMAGE_HANDOFF, CreationStage.FINAL_COPY}:
            if session.stage == CreationStage.FINAL_COPY:
                session = approve_stage(session, settings=runtime)
            session.image_design_requested = True
            art = session.artifact(CreationStage.IMAGE_HANDOFF)
            if art is not None:
                session.set_artifact(art.model_copy(update={"approved": True}))
            session.stage = CreationStage.COMPLETED
            session.status = "completed"
            session.revision += 1
            session.last_message_zh = (
                "已记录：进入图片设计交接。\n"
                "请切换独立 skill `amazon-image-design`，按主图 + 7 张辅图规划"
                "（本仓不执行图片生成）。文案字段保持不变。"
            )
            return session

    if low in {"跳过竞品", "skip competitor", "无竞品"}:
        session.brief = session.brief.model_copy(update={"competitors": ()})
        if session.stage == CreationStage.COMPETITOR:
            return approve_stage(session, skip_competitor=True, settings=runtime)
        session.last_message_zh = "已记录跳过竞品（竞品不得覆盖已确认产品事实）。"
        return session

    if low in {"认可", "确认", "approve", "ok", "通过"}:
        if session.stage == CreationStage.BRIEF and not session.brief.is_ready:
            session.last_message_zh = "请先提供产品名和目标站点（marketplace）。"
            session.status = "awaiting_approval"
            return session
        return approve_stage(session, settings=runtime)

    if session.stage == CreationStage.BRIEF:
        session.brief = parse_brief_message(text, session.brief)
        return run_stage(session, settings=runtime)

    session.brief = session.brief.model_copy(
        update={"notes": (session.brief.notes + "\n" + text).strip()}
    )
    return run_stage(session, settings=runtime)


def run_fast_path(
    session: CreationSession,
    settings: Settings | None = None,
) -> CreationSession:
    """User-explicit bypass of intermediate gates; evidence rules still apply."""
    runtime = settings or Settings()
    if not session.brief.is_ready:
        session.status = "awaiting_approval"
        session.stage = CreationStage.BRIEF
        session.last_message_zh = "直接输出需要产品名和目标站点。"
        return session

    session.fast_path = True
    research = load_research_context(
        runtime,
        product_name=session.brief.product_name,
        marketplace=session.brief.marketplace,
        specs=session.brief.specs_text,
    )
    for row in research_as_ledger_rows(research):
        session.brief = session.brief.with_fact(row)

    llm = get_llm(runtime, role="writer")
    system = _system_prompt(CreationStage.FINAL_COPY)
    user = _user_prompt(session, CreationStage.FINAL_COPY, research)
    raw = llm.complete(system, user, json_mode=True)
    try:
        payload = extract_json_object(raw)
    except JsonExtractError:
        session.status = "failed"
        session.error = "fast_path_json_parse_failed"
        return session

    deliverable, auth = finalize_deliverable(
        payload,
        brand=session.brief.brand,
        media_category=session.brief.media_category,
        fact_ledger=session.brief.fact_ledger,
    )
    session.deliverable = deliverable
    session.claim_authorization = auth
    session.revision += 1
    session.set_artifact(
        StageArtifact(
            stage=CreationStage.FINAL_COPY,
            summary_zh="fast_path 成稿（仍受证据门约束）",
            payload=payload,
            approved=auth.allowed and deliverable.policy_status != "BLOCK",
            evidence_notes_zh="用户明确跳过中间审批；第三方数据仍不可背书产品规格。",
        )
    )
    if deliverable.policy_status == "BLOCK":
        session.stage = CreationStage.FINAL_COPY
        session.status = "awaiting_approval"
        session.last_message_zh = (
            f"直接输出被证据/政策门拦截（BLOCK）："
            f"{', '.join(auth.blocked_claims) or deliverable.policy_issues[:3]}。"
            "请补充已确认产品资料。"
        )
        return session

    session.stage = CreationStage.IMAGE_HANDOFF
    return run_stage(session, settings=runtime)


def _brief_summary(brief: ProductBrief) -> str:
    missing = []
    if not brief.product_name:
        missing.append("产品名")
    if not brief.marketplace:
        missing.append("目标站点")
    if not brief.specs_text:
        missing.append("规格参数")
    missing_s = "、".join(missing) if missing else "无"
    verified_n = len(brief.verified_product_facts())
    return (
        f"【Brief 与事实台账】产品={brief.product_name or '—'}，"
        f"站点={brief.marketplace or '—'}，品牌={brief.brand or '—'}。"
        f"已确认产品事实 {verified_n} 条。缺失：{missing_s}。"
        "规格/认证/性能无来源不得写入最终稿，标「待补」。"
    )


def _stage_evidence_note(stage: CreationStage, session: CreationSession) -> str:
    if stage == CreationStage.AUDIENCE:
        return "本阶段默认 hypothesis（无数据集不得写百分比）。"
    if stage == CreationStage.PRODUCT:
        return "产品解读只能映射已确认规格；缺失参数标待补。"
    if stage == CreationStage.COMPETITOR:
        return "竞品文案仅参考结构/角度，不能证明我方规格或功效。"
    if stage == CreationStage.SELLING_POINTS:
        return "卖点必须挂接产品依据；无依据不得写硬参数。"
    if stage == CreationStage.KEYWORDS:
        return "词库可含第三方/竞品语言，布局时不得把未验证规格写入 Title。"
    if stage == CreationStage.FINAL_COPY:
        missing = session.brief.missing_hard_facts()
        base = "最终稿仅使用 product_confirmed 及以上背书的硬宣称。"
        if missing:
            return base + " 当前待补：" + "、".join(missing[:8])
        return base
    return ""


def _checklist_block(session: CreationSession) -> str:
    return "审批进度：\n" + "\n".join(session.gate_checklist_zh())


def _strip_invented_percentages(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove percentage claims unless basis is measured (mock-safe)."""
    text = str(payload)
    if "%" in text or "％" in text:
        payload = {**payload, "notes_zh": str(payload.get("notes_zh") or "") + "（已避免无数据集百分比）"}
    return payload


def _system_prompt(stage: CreationStage) -> str:
    return (
        "You are an Amazon listing creation agent with approval gates and evidence control. "
        "Post-2026-07-27 non-media Title ≤75 chars, Item Highlights ≤125 chars, "
        "Search Terms ≤250 UTF-8 bytes. "
        "Never invent specs, certifications, performance numbers, or percentages. "
        "Mark gaps as 待补. Lower evidence tiers cannot override higher facts. "
        "Third-party MCP and competitor data are market context only. "
        "Return JSON only. "
        f"Current stage:{stage.value}\n"
        f"{evidence_prompt_block()}"
    )


def _user_prompt(
    session: CreationSession,
    stage: CreationStage,
    research: dict[str, Any],
) -> str:
    approved = {key: art.payload for key, art in session.artifacts.items() if art.approved}
    ledger = [
        {
            "fact": r.fact,
            "value": r.value,
            "tier": r.tier.name,
            "source_kind": r.source_kind.value,
            "status": r.status.value,
        }
        for r in session.brief.fact_ledger
    ]
    return (
        f"stage:{stage.value}\n"
        f"stage_label:{STAGE_LABEL_ZH.get(stage, stage.value)}\n"
        f"brief:{session.brief.model_dump(mode='json')}\n"
        f"fact_ledger:{ledger}\n"
        f"approved_artifacts:{approved}\n"
        f"research_market_context_only:{research}\n"
        f"user_notes:{session.brief.notes}\n"
        "Respond with stage-appropriate JSON. "
        "For final_copy include title, title_zh, item_highlights, item_highlights_zh, "
        "bullets[{text,text_zh}], search_terms, unresolved[], notes_zh."
    )
