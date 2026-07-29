"""Frozen allowlist for the packaged Amazon copy-optimization snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping


@unique
class ContractMarketplace(StrEnum):
    """Marketplaces covered by the packaged baseline."""

    US = "US"
    UK = "UK"


@unique
class ContractResourceKind(StrEnum):
    """Closed resource variants with deterministic package locations."""

    SKILL = "skill"
    PRODUCT_PROFILE = "product_profile"
    PROCESS_PROFILE = "process_profile"
    KEYWORD_AUDIT_CLI = "keyword_audit_cli"
    OUTPUT_TEMPLATE = "output_template"


@unique
class AuthorityClass(StrEnum):
    """Authority carried by the approved internal snapshot."""

    INTERNAL_NON_AUTHORITATIVE = "internal_non_authoritative"


_RESOURCE_DIRECTORIES: Final[Mapping[ContractResourceKind, str]] = MappingProxyType(
    {
        ContractResourceKind.SKILL: "",
        ContractResourceKind.PRODUCT_PROFILE: "references",
        ContractResourceKind.PROCESS_PROFILE: "references",
        ContractResourceKind.KEYWORD_AUDIT_CLI: "scripts",
        ContractResourceKind.OUTPUT_TEMPLATE: "templates",
    }
)


@dataclass(frozen=True, slots=True)
class ContractResource:
    """One immutable allowlisted resource and its routing metadata."""

    version: str
    filename: str
    kind: ContractResourceKind
    marketplaces: tuple[ContractMarketplace, ...]
    product_types: tuple[str, ...]
    sha256: str
    authority_class: AuthorityClass

    @property
    def relative_path(self) -> PurePosixPath:
        """Resolve only the directory fixed by the typed resource kind."""
        return PurePosixPath(_RESOURCE_DIRECTORIES[self.kind], self.filename)

    @property
    def is_profile(self) -> bool:
        """Return whether this entry is a packaged Markdown profile."""
        return self.kind in {
            ContractResourceKind.PRODUCT_PROFILE,
            ContractResourceKind.PROCESS_PROFILE,
        }

    @property
    def can_authorize_facts(self) -> Literal[False]:
        """Prevent internal guidance from authorizing product facts."""
        return False


CONTRACT_VERSION: Final = "1.4.4"
_AUTHORITY: Final = AuthorityClass.INTERNAL_NON_AUTHORITATIVE
_US: Final = (ContractMarketplace.US,)
_UK: Final = (ContractMarketplace.UK,)
_US_UK: Final = (ContractMarketplace.US, ContractMarketplace.UK)

CONTRACT_MANIFEST: Final[tuple[ContractResource, ...]] = (
    ContractResource(
        CONTRACT_VERSION,
        "SKILL.md",
        ContractResourceKind.SKILL,
        _US_UK,
        (),
        "c4bf73cecf788e326018e51631cc9429d8e39487885b9d20959d516339d8c417",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "amazon-public-pdp-and-autocomplete-fallback.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US_UK,
        (),
        "4b68f9d37aef0d0b84ae57498f1e58675873162413b41683c71cc2a1900a2d06",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "cosmo-rufus-copy-rules.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US_UK,
        (),
        "58f01adc380d628129828358048bd4cf8ce47b8303976f80ec0dd0276ff9281a",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "parent-child-variation-copy.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US_UK,
        (),
        "55797b69adb6cd77b235b8a2de0bf2bc8718f6148d0af95a64c63be8e34d2b5c",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "structured-fact-authorization-and-cascade-dedupe.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US_UK,
        (),
        "7859d2b772956b6ac0742112b3e509cdcd945c7afbfd36888fbe05c100a5c74b",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "short-title-highlight-search-term-allocation.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US_UK,
        (),
        "b4ae074aa773cca59ea8fd9f59457eb62ab3dc21d6c7b2131f54a741cccad822",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "uk-bakery-packaging-copy.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _UK,
        ("BAKERY_PACKAGING",),
        "e43fbc868c79f48ad5dce9bdf62838a514eac9c38e676686d687187c7d559ba0",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "uk-cellophane-hamper-copy.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _UK,
        ("CELLOPHANE_HAMPER",),
        "bedff5db28f60184a751b9315adeedc15e3c7302dd37ca3e8dcf457241a91de8",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-adjustable-wedding-sign-stands.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("SIGN_DISPLAY_STAND",),
        "a09ff9446073803ac942bfae64d821e725bfd44e73808ecc1d6ffe5a4c19a43a",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-childrens-swim-aid-listing-audit.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("SWIM_VEST",),
        "eee3f918be07132187f98b5b46f2b681d1d9a10dd5f7180a58c088958aed494b",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-decorative-wired-ribbon-short-fields.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("DECORATIVE_WIRED_RIBBON",),
        "b6ffda3f8d8fe8188eece8451154055cdbae565882545a57a739839b31bf86d3",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-metal-magazine-file-holder-copy.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("MAGAZINE_FILE_HOLDER",),
        "c82cc11b2a143cc57cebd48639202b69fb88b7289b01aa9de405447843e5612c",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-multifunction-desk-organizer-copy.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("DESK_ORGANIZER",),
        "155af3e362b37d20436888d76211bf63d1201e80e9c24797b7c2e0c45be51139",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-natural-scallop-shell-copy.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("NATURAL_SCALLOP_SHELL",),
        "046cb028634f4cc377183ec2e18900fc284b2ad15b2f823da365a6054b0b1ae2",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-outdoor-bird-bath-short-fields.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("OUTDOOR_BIRD_BATH",),
        "5bb22ad10ec43b34c69eb2d0defa4bff400beac304ed15b82aae1fa5638a51b9",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-short-field-office-organizer-examples.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("OFFICE_ORGANIZER",),
        "55f8757c36e7080eb159fb66a7eec7ebf7889b2df3e2f7378dc3a9e215f36d89",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-short-title-highlight-search-terms.md",
        ContractResourceKind.PROCESS_PROFILE,
        _US,
        (),
        "b5ff38c0bc3c3c5c2a35c76a5094a0adc94d0d206a46880297cfb5e7b0e3df15",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-small-mesh-zipper-pouches.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("MESH_ZIPPER_POUCH",),
        "b436620ce8ebd592d8882f464fd8bfaabe023845480f22a93c5f4417db407701",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-tiered-letter-tray-organizers.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("LETTER_TRAY_ORGANIZER",),
        "7084ee9333c09d7a0f17839e5fe0c5e458e1dc3a45a3922ab17ff6d21109acfd",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-wall-file-organizer-short-fields.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("WALL_FILE_ORGANIZER",),
        "06270e0e4dc674891985836b5f59a1216a651ab458c5dfa8c6b60481e4f4b5e5",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "wood-wall-panel-keyword-gap-seo.md",
        ContractResourceKind.PRODUCT_PROFILE,
        _US,
        ("WOOD_WALL_PANEL",),
        "3e9aa26feb0f874e8a4cf4024b5eca0acee57bff1d594b8ac0dbe7acb97f9be2",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "audit_keyword_embedding.py",
        ContractResourceKind.KEYWORD_AUDIT_CLI,
        _US_UK,
        (),
        "c9d6230df0f13d73334eaecb80613be6a1b73ce2a06640fd71550229e0dfa6c7",
        _AUTHORITY,
    ),
    ContractResource(
        CONTRACT_VERSION,
        "us-full-listing-optimization-output.md",
        ContractResourceKind.OUTPUT_TEMPLATE,
        _US,
        (),
        "9b2e8f6cce41e74b7537de35abda6a422de13350d8949d610509dcc1d04a3faa",
        _AUTHORITY,
    ),
)

PROFILE_RESOURCES: Final[tuple[ContractResource, ...]] = tuple(
    resource for resource in CONTRACT_MANIFEST if resource.is_profile
)

__all__ = [
    "CONTRACT_MANIFEST",
    "CONTRACT_VERSION",
    "PROFILE_RESOURCES",
    "AuthorityClass",
    "ContractMarketplace",
    "ContractResource",
    "ContractResourceKind",
]
