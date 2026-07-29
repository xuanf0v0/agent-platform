"""Catalog product types and deterministic title heuristics for specialized routing."""

from __future__ import annotations

from typing import Final

from amazon_copy.specialized_rules.catalog import RULE_PROFILES, Marketplace

# Title/body phrase → product type (longer phrases first; casefold match).
_HEURISTIC_SIGNALS: Final[tuple[tuple[str, str], ...]] = (
    ("acoustic wood slat", "ACOUSTIC_WOOD_SLAT_WALL_PANEL"),
    ("wood slat wall panel", "ACOUSTIC_WOOD_SLAT_WALL_PANEL"),
    ("acoustic wood panel", "ACOUSTIC_WOOD_SLAT_WALL_PANEL"),
    ("acoustic polyester panel", "ACOUSTIC_POLYESTER_PANEL"),
    ("polyester acoustic panel", "ACOUSTIC_POLYESTER_PANEL"),
    ("wedding welcome sign stand", "SIGN_DISPLAY_STAND"),
    ("wedding sign stand", "SIGN_DISPLAY_STAND"),
    ("welcome sign stand", "SIGN_DISPLAY_STAND"),
    ("sign display stand", "SIGN_DISPLAY_STAND"),
    ("decorative wired ribbon", "DECORATIVE_WIRED_RIBBON"),
    ("wired ribbon", "DECORATIVE_WIRED_RIBBON"),
    ("magazine file holder", "MAGAZINE_FILE_HOLDER"),
    ("magazine holder", "MAGAZINE_FILE_HOLDER"),
    ("desk organizer", "DESK_ORGANIZER"),
    ("desktop organizer", "DESK_ORGANIZER"),
    ("desktop storage", "DESK_ORGANIZER"),
    ("modular desk", "DESK_ORGANIZER"),
    ("desk storage", "DESK_ORGANIZER"),
    ("natural scallop shell", "NATURAL_SCALLOP_SHELL"),
    ("scallop shell", "NATURAL_SCALLOP_SHELL"),
    ("outdoor bird bath", "OUTDOOR_BIRD_BATH"),
    ("bird bath", "OUTDOOR_BIRD_BATH"),
    ("mesh zipper pouch", "MESH_ZIPPER_POUCH"),
    ("zipper pouch", "MESH_ZIPPER_POUCH"),
    ("letter tray", "LETTER_TRAY_ORGANIZER"),
    ("tiered letter tray", "LETTER_TRAY_ORGANIZER"),
    ("wall file organizer", "WALL_FILE_ORGANIZER"),
    ("wall file", "WALL_FILE_ORGANIZER"),
    ("wood wall panel", "WOOD_WALL_PANEL"),
    ("wooden wall panel", "WOOD_WALL_PANEL"),
    ("hardware cloth", "HARDWARE_CLOTH"),
    ("office organizer", "OFFICE_ORGANIZER"),
    ("bakery packaging", "BAKERY_PACKAGING"),
    ("cellophane hamper", "CELLOPHANE_HAMPER"),
    ("hamper wrap", "CELLOPHANE_HAMPER"),
    ("a5 hardback", "A5_HARDBACK_LINED_NOTEBOOK"),
    ("hardback lined notebook", "A5_HARDBACK_LINED_NOTEBOOK"),
    ("rotating pen holder", "ROTATING_PEN_HOLDER"),
    ("acrylic pen holder", "ROTATING_PEN_HOLDER"),
    ("craft kit", "CRAFT_KIT"),
    ("dust mop refill", "DUST_MOP_REFILL_PAD"),
    ("mop refill pad", "DUST_MOP_REFILL_PAD"),
    ("document wallet", "DOCUMENT_WALLET"),
    ("plastic wallet", "DOCUMENT_WALLET"),
    ("writing pad", "WRITING_PAD"),
    ("cellophane gift", "CELLOPHANE_GIFT_PACKAGING"),
    ("self adhesive cellophane", "SELF_ADHESIVE_CELLOPHANE_BAG"),
    ("cellophane bag", "SELF_ADHESIVE_CELLOPHANE_BAG"),
    ("swim vest", "SWIM_VEST"),
    ("life jacket", "SWIM_VEST"),
    ("flotation vest", "SWIM_VEST"),
    ("painting rock", "ART_CRAFT_MATERIAL"),
    ("river rock", "ART_CRAFT_MATERIAL"),
    ("craft stone", "ART_CRAFT_MATERIAL"),
)

_PRODUCT_TYPE_LABELS_ZH: Final[dict[str, str]] = {
    "SIGN_DISPLAY_STAND": "婚礼/活动欢迎牌展示支架",
    "SWIM_VEST": "儿童泳助/救生衣类",
    "DECORATIVE_WIRED_RIBBON": "装饰铁丝边丝带",
    "MAGAZINE_FILE_HOLDER": "金属杂志架/文件架",
    "DESK_ORGANIZER": "多功能桌面收纳",
    "NATURAL_SCALLOP_SHELL": "天然扇贝壳",
    "OUTDOOR_BIRD_BATH": "户外鸟浴盆",
    "MESH_ZIPPER_POUCH": "网眼拉链袋",
    "LETTER_TRAY_ORGANIZER": "层叠信盘/文件盘",
    "WALL_FILE_ORGANIZER": "墙面文件架",
    "WOOD_WALL_PANEL": "木墙板",
    "ACOUSTIC_WOOD_SLAT_WALL_PANEL": "吸音木条墙板",
    "ACOUSTIC_POLYESTER_PANEL": "聚酯吸音板",
    "HARDWARE_CLOTH": "铁丝网/hardware cloth",
    "OFFICE_ORGANIZER": "办公短字段收纳",
    "BAKERY_PACKAGING": "烘焙包装",
    "CELLOPHANE_HAMPER": "玻璃纸礼篮包装",
    "A5_HARDBACK_LINED_NOTEBOOK": "A5 精装横线笔记本",
    "ROTATING_PEN_HOLDER": "旋转亚克力笔筒",
    "CRAFT_KIT": "手工/工艺套装",
    "DUST_MOP_REFILL_PAD": "除尘拖把替换垫",
    "DOCUMENT_WALLET": "塑料文件袋",
    "WRITING_PAD": "书写本/拍纸本",
    "CELLOPHANE_GIFT_PACKAGING": "玻璃纸礼品包装",
    "SELF_ADHESIVE_CELLOPHANE_BAG": "自粘玻璃纸袋",
    "ART_CRAFT_MATERIAL": "绘画石/工艺石材",
    "GENERAL_PRODUCT": "通用商品（无专项）",
}


def catalog_product_types(marketplace: str | Marketplace | None = None) -> tuple[str, ...]:
    """Return sorted unique product types from the specialized catalog."""
    market: Marketplace | None = None
    if isinstance(marketplace, Marketplace):
        market = marketplace
    elif isinstance(marketplace, str) and marketplace.strip():
        try:
            market = Marketplace(marketplace.strip().upper())
        except ValueError:
            market = None
    types: set[str] = set()
    for profile in RULE_PROFILES:
        if profile.kind != "product":
            continue
        if market is not None and market not in profile.marketplaces:
            continue
        types.update(profile.product_types)
    return tuple(sorted(types))


def product_type_label_zh(product_type: str) -> str:
    """Chinese short label for prompts and UI."""
    return _PRODUCT_TYPE_LABELS_ZH.get(product_type, product_type)


def infer_product_type_heuristic(text: str) -> str | None:
    """Infer product type from listing text via ordered phrase signals."""
    folded = text.casefold()
    for phrase, product_type in _HEURISTIC_SIGNALS:
        if phrase in folded:
            return product_type
    return None


def is_catalog_product_type(product_type: str, marketplace: str | None = None) -> bool:
    """Return whether product_type is an exact catalog key for the marketplace."""
    normalized = product_type.strip().upper()
    if not normalized or normalized == "GENERAL_PRODUCT":
        return False
    return normalized in set(catalog_product_types(marketplace))


__all__ = [
    "catalog_product_types",
    "infer_product_type_heuristic",
    "is_catalog_product_type",
    "product_type_label_zh",
]
