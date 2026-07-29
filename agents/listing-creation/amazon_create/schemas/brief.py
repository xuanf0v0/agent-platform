"""Product brief and fact ledger."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from amazon_create.schemas.evidence import (
    EvidenceSourceKind,
    FactRow,
    FactStatus,
    merge_fact_rows,
)


class ProductBrief(BaseModel):
    """Minimum brief for staged creation, with tiered fact ledger."""

    model_config = ConfigDict(frozen=True)

    product_name: str = ""
    marketplace: str = ""
    language: str = "en"
    brand: str = ""
    product_type: str = ""
    media_category: bool = False
    media_status_confirmed: bool = False
    listing_scope: str = "parent"
    listing_scope_confirmed: bool = False
    variation_values: dict[str, str] = Field(default_factory=dict)
    product_asin: str = ""
    specs_text: str = ""
    competitors: tuple[str, ...] = ()
    keywords_seed: tuple[str, ...] = ()
    tone: str = ""
    forbidden_phrases: tuple[str, ...] = ()
    notes: str = ""
    fact_ledger: tuple[FactRow, ...] = ()
    sensitive_category: bool = False

    @property
    def is_ready(self) -> bool:
        """True when product name and marketplace are present."""
        return bool(self.product_name.strip() and self.marketplace.strip())

    def required_context_missing(self) -> tuple[str, ...]:
        """Fields that materially change policy, localization, or variation handling."""
        missing: list[str] = []
        if not self.product_name.strip():
            missing.append("产品名")
        if not self.marketplace.strip():
            missing.append("目标站点")
        if not self.language.strip():
            missing.append("目标语言")
        if not self.product_type.strip():
            missing.append("产品类型/类目")
        if not self.media_status_confirmed:
            missing.append("是否 media 类目")
        if not self.listing_scope_confirmed:
            missing.append("父体/子体范围")
        return tuple(missing)

    def with_fact(self, row: FactRow) -> ProductBrief:
        """Return brief with merged ledger row (higher tier wins)."""
        return self.model_copy(update={"fact_ledger": merge_fact_rows(self.fact_ledger, row)})

    def verified_product_facts(self) -> tuple[FactRow, ...]:
        return tuple(
            row
            for row in self.fact_ledger
            if row.status == FactStatus.VERIFIED
            and row.source_kind
            in {
                EvidenceSourceKind.PRODUCT_CONFIRMED,
                EvidenceSourceKind.LEGAL_SAFETY,
                EvidenceSourceKind.AMAZON_OFFICIAL,
                EvidenceSourceKind.BRAND_FIRST_PARTY,
            }
        )

    def missing_hard_facts(self) -> tuple[str, ...]:
        from amazon_create.schemas.evidence import HARD_CLAIM_KEYS

        missing: list[str] = []
        for row in self.fact_ledger:
            if row.status in {FactStatus.MISSING, FactStatus.HYPOTHESIS}:
                if any(t in row.fact.casefold() for t in HARD_CLAIM_KEYS):
                    missing.append(row.fact)
        if not self.specs_text.strip() and "specs_text" not in {
            r.fact for r in self.fact_ledger if r.status == FactStatus.VERIFIED
        }:
            missing.append("specs_text")
        return tuple(dict.fromkeys(missing))
