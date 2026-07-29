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
