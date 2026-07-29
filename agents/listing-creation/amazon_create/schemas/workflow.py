"""Staged creation session state machine with approval gates."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from amazon_create.schemas.brief import ProductBrief
from amazon_create.schemas.deliverable import CreationDeliverable, ImageDesignPlan
from amazon_create.schemas.evidence import EVIDENCE_POLICY, ClaimAuthorizationResult


class CreationStage(StrEnum):
    """Ordered approval gates for listing creation."""

    BRIEF = "brief"
    AUDIENCE = "audience"
    PRODUCT = "product"
    COMPETITOR = "competitor"
    SELLING_POINTS = "selling_points"
    KEYWORDS = "keywords"
    FINAL_COPY = "final_copy"
    IMAGE_HANDOFF = "image_handoff"
    IMAGE_ANALYSIS = "image_analysis"
    IMAGE_PLAN = "image_plan"
    COMPLETED = "completed"


STAGE_ORDER: tuple[CreationStage, ...] = (
    CreationStage.BRIEF,
    CreationStage.AUDIENCE,
    CreationStage.PRODUCT,
    CreationStage.COMPETITOR,
    CreationStage.SELLING_POINTS,
    CreationStage.KEYWORDS,
    CreationStage.FINAL_COPY,
    CreationStage.IMAGE_HANDOFF,
    CreationStage.IMAGE_ANALYSIS,
    CreationStage.IMAGE_PLAN,
    CreationStage.COMPLETED,
)

STAGE_LABEL_ZH: dict[CreationStage, str] = {
    CreationStage.BRIEF: "Brief 与事实台账",
    CreationStage.AUDIENCE: "受众与市场审批",
    CreationStage.PRODUCT: "产品解读审批",
    CreationStage.COMPETITOR: "竞品分析审批",
    CreationStage.SELLING_POINTS: "五大卖点审批",
    CreationStage.KEYWORDS: "关键词与意图库审批",
    CreationStage.FINAL_COPY: "最终文案审批",
    CreationStage.IMAGE_HANDOFF: "图片设计交接",
    CreationStage.IMAGE_ANALYSIS: "图片组分析审批",
    CreationStage.IMAGE_PLAN: "主图与七张辅图审批",
    CreationStage.COMPLETED: "已完成",
}


class StageArtifact(BaseModel):
    """Approved or draft artifact for one stage."""

    model_config = ConfigDict(frozen=True)

    stage: CreationStage
    summary_zh: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    evidence_notes_zh: str = ""


class CreationSession(BaseModel):
    """Mutable session stored in Streamlit or service callers."""

    model_config = ConfigDict(frozen=False)

    session_id: str = Field(default_factory=lambda: uuid4().hex)
    revision: int = 0
    stage: CreationStage = CreationStage.BRIEF
    brief: ProductBrief = Field(default_factory=ProductBrief)
    artifacts: dict[str, StageArtifact] = Field(default_factory=dict)
    deliverable: CreationDeliverable | None = None
    claim_authorization: ClaimAuthorizationResult | None = None
    fast_path: bool = False
    status: Literal[
        "active",
        "awaiting_approval",
        "awaiting_facts",
        "completed",
        "failed",
    ] = "active"
    last_message_zh: str = ""
    error: str = ""
    image_design_requested: bool | None = None
    image_task_type: str = "image_design"
    image_asset_count: int = 0
    image_design_plan: ImageDesignPlan | None = None
    human_review_confirmed: bool = False
    active_rule_files: tuple[str, ...] = ()

    def artifact(self, stage: CreationStage) -> StageArtifact | None:
        return self.artifacts.get(stage.value)

    def set_artifact(self, artifact: StageArtifact) -> None:
        self.artifacts[artifact.stage.value] = artifact

    def approved_stages(self) -> list[CreationStage]:
        return [
            CreationStage(key)
            for key, art in self.artifacts.items()
            if art.approved and key in {s.value for s in CreationStage}
        ]

    def gate_checklist_zh(self) -> list[str]:
        lines: list[str] = []
        for stage in STAGE_ORDER:
            if stage == CreationStage.COMPLETED:
                continue
            art = self.artifact(stage)
            if stage == self.stage and self.status == "awaiting_approval":
                mark = "▶"
            elif art and art.approved:
                mark = "✓"
            elif stage == self.stage:
                mark = "…"
            else:
                mark = "○"
            lines.append(f"{mark} {STAGE_LABEL_ZH[stage]}")
        return lines

    def evidence_policy_zh(self) -> list[str]:
        return list(EVIDENCE_POLICY.order_zh) + list(EVIDENCE_POLICY.rules_zh)
