"""Deterministic offline LLM for staged creation."""

from __future__ import annotations

import json
from typing import Any


class MockLLM:
    """Role-aware fixture completions for creation stages."""

    def __init__(self, role: str = "writer") -> None:
        self._role = role
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        self._call_count += 1
        _ = system, kwargs
        payload = _stage_payload(user)
        return json.dumps(payload, ensure_ascii=False)


def _stage_payload(user: str) -> dict[str, Any]:
    text = user.casefold()
    if "stage:image_analysis" in text:
        return {
            "source_analysis": [
                "No retrievable product image group in fixture mode; request ASIN-backed images or uploads",
                "Reuse approved selling points and buyer concerns as the image hierarchy",
            ],
            "image_scores": {
                "platform_compliance": 0,
                "selling_point_clarity": 0,
                "dimensions_resolution": 0,
                "color_palette": 0,
                "background_design": 0,
                "layout": 0,
                "detail_optimization": 0,
                "image_copy": 0,
            },
            "upload_requests": ["产品白底图或产品 ASIN", "现有图片组（如无法通过 ASIN 获取）"],
            "compliance_notes": ["主图纯白背景、无文字、产品约占画面 85%"],
            "notes_zh": "离线模式无法抓取真实图片，已明确所需素材。",
        }
    if "stage:image_plan" in text:
        images = [
            {
                "image": "Main Image",
                "selling_point": "Complete product presentation",
                "color_palette": "True product colors",
                "product_angle": "Three-quarter full-product view",
                "background": "Pure white RGB 255,255,255",
                "layout": "Product fills about 85% of frame",
                "detail_treatment": "Sharp edges and accurate texture",
                "image_copy": "No text",
            }
        ]
        for index in range(1, 8):
            images.append(
                {
                    "image": f"Secondary {index}",
                    "selling_point": f"Approved selling point {index}",
                    "color_palette": "Brand-aligned cyan and neutral accents",
                    "product_angle": "Detail or relevant use angle",
                    "background": "Clean scenario or detail background",
                    "layout": "One dominant message with supporting detail",
                    "detail_treatment": "Highlight verified product evidence",
                    "image_copy": f"Verified benefit {index}",
                }
            )
        return {
            "task_type": "image_design",
            "research_basis": ["approved listing artifacts", "fixture image analysis"],
            "source_analysis": ["Image plan requires real asset verification before production"],
            "image_scores": {
                "platform_compliance": 8.0,
                "selling_point_clarity": 8.0,
                "dimensions_resolution": 8.0,
                "color_palette": 8.0,
                "background_design": 8.0,
                "layout": 8.0,
                "detail_optimization": 8.0,
                "image_copy": 8.0,
            },
            "images": images,
            "upload_requests": ["High-resolution product photography"],
            "compliance_notes": ["Verify every visible accessory is included"],
        }
    if "stage:audience" in text or "audience research" in text:
        return {
            "audiences": [
                {
                    "segment": "DIY homeowners",
                    "scenarios": ["garden fence", "chicken coop"],
                    "basis": "hypothesis",
                }
            ],
            "motivations": [
                {"theme": "pest barrier", "basis": "hypothesis"},
                {"theme": "durability", "basis": "hypothesis"},
            ],
            "concerns": [
                {"theme": "rust", "basis": "hypothesis"},
                {"theme": "mesh size fit", "basis": "hypothesis"},
            ],
            "cosmo_intents": [
                "core_need: barrier mesh",
                "scenario: poultry run",
                "attribute: gauge and opening",
                "care: cut and install safely",
            ],
            "notes_zh": "无实时评论数据时为定性假设，已标注 hypothesis。",
        }
    if "stage:product" in text or "product interpretation" in text:
        return {
            "category_comparison_dims": [
                "mesh opening",
                "wire gauge",
                "roll size",
                "finish",
                "use case",
            ],
            "mappings": [
                {
                    "param": "mesh size",
                    "buyer_care": "pest exclusion",
                    "intent": "small animal barrier",
                    "safe_copy": "designed for garden and coop barrier use",
                    "gap": "待补 if exact opening missing",
                }
            ],
            "notes_zh": "按参数映射意图；缺失规格保持待补。",
        }
    if "stage:competitor" in text or "competitor analysis" in text:
        return {
            "competitors": [],
            "opportunities": [
                "Lead with verified gauge and mesh",
                "Cover install and safety without absolutes",
            ],
            "notes_zh": "未提供竞品 ASIN 时仅输出机会假设。",
        }
    if "stage:selling_points" in text or "selling points" in text:
        return {
            "selling_points": [
                {
                    "rank": 1,
                    "point": "Heavy-duty gauge strength",
                    "pain": "thin mesh bends",
                    "evidence": "user brief gauge if provided else 待补",
                    "terms": ["heavy duty", "gauge"],
                    "safe_claim": "built for demanding outdoor projects",
                },
                {
                    "rank": 2,
                    "point": "Small-mesh pest barrier",
                    "pain": "rabbits/gophers",
                    "evidence": "mesh opening 待补",
                    "terms": ["garden fence", "pest barrier"],
                    "safe_claim": "helps keep small pests out of beds and runs",
                },
                {
                    "rank": 3,
                    "point": "Galvanized outdoor finish",
                    "pain": "rust worry",
                    "evidence": "finish 待补",
                    "terms": ["galvanized", "outdoor"],
                    "safe_claim": "designed to help resist rust in outdoor use",
                },
                {
                    "rank": 4,
                    "point": "Project-ready roll size",
                    "pain": "wrong dimensions",
                    "evidence": "size 待补",
                    "terms": ["roll", "cut to fit"],
                    "safe_claim": "cut-to-fit roll for DIY panels and guards",
                },
                {
                    "rank": 5,
                    "point": "Straightforward install with care",
                    "pain": "sharp wire risk",
                    "evidence": "install tools",
                    "terms": ["DIY", "install"],
                    "safe_claim": "use gloves and eye protection when cutting",
                },
            ],
            "notes_zh": "五大卖点按意图排序，缺规格处已标待补。",
        }
    if "stage:keywords" in text:
        return {
            "core_keywords": ["hardware cloth", "welded wire mesh", "garden fence"],
            "roots": ["mesh", "fence", "coop", "garden", "galvanized"],
            "semantic_terms": ["chicken coop", "raised bed", "pest barrier", "cut to fit"],
            "qa_questions": [
                "What mesh size is it?",
                "Is it suitable for a chicken coop?",
                "How do I cut and install it?",
            ],
            "allocation": {
                "title": ["hardware cloth", "critical spec"],
                "item_highlights": ["material", "use cases"],
                "bullets": ["intent clusters"],
                "search_terms": ["synonyms residual"],
            },
            "notes_zh": "关键词与意图库（第三方数据仅作市场上下文）。",
        }
    # Final copy default (stage:final_copy or unspecified)
    return {
        "title": "Brand Hardware Cloth Welded Wire Mesh Roll",
        "title_zh": "品牌铁丝网焊接卷材",
        "item_highlights": (
            "Galvanized welded mesh for chicken coops, garden beds, and DIY outdoor barriers"
        ),
        "item_highlights_zh": "镀锌焊接网，适用于鸡舍、花坛与户外 DIY 防护",
        "bullets": [
            {
                "text": (
                    "HEAVY-DUTY MESH - Built for demanding outdoor barrier projects; "
                    "choose the verified gauge from your pack specs before install"
                ),
                "text_zh": "重型网片 - 面向严苛户外防护项目；安装前请核对包装上的真实线径",
            },
            {
                "text": (
                    "PEST BARRIER USE - Helps keep small pests out of garden beds, "
                    "poultry runs, and raised planters when mesh opening matches the pest"
                ),
                "text_zh": "防护用途 - 在网孔匹配目标害虫时，有助于保护花坛、禽舍与抬高种植床",
            },
            {
                "text": (
                    "OUTDOOR FINISH - Galvanized welded construction designed to help "
                    "resist rust in damp garden and coop environments"
                ),
                "text_zh": "户外镀层 - 镀锌焊接结构，面向潮湿花园与禽舍环境，有助于减缓锈蚀",
            },
            {
                "text": (
                    "PROJECT ROLL - Cut-to-fit roll for coop panels, tree guards, vents, "
                    "and DIY fence sections; confirm width and length on the label"
                ),
                "text_zh": "工程卷材 - 可按需裁切用于禽舍板、护树、通风口与 DIY 围栏；请核对标签尺寸",
            },
            {
                "text": (
                    "INSTALL WITH CARE - Use wire cutters, staples or zip ties; wear gloves "
                    "and eye protection when cutting and handling sharp edges"
                ),
                "text_zh": "安全安装 - 使用钢丝钳、U 钉或扎带；裁切与搬运时佩戴手套与护目镜",
            },
        ],
        "search_terms": (
            "welded wire mesh chicken wire garden fencing poultry run rabbit hutch "
            "raised bed barrier tree guard crawl space vent diy hardware cloth roll"
        ),
        "product_description": (
            "Built for practical outdoor DIY projects, this welded wire mesh supports "
            "garden, coop, vent, and barrier applications when the verified size and gauge "
            "match the project. Confirm package specifications before cutting, then install "
            "with suitable fasteners while wearing gloves and eye protection."
        ),
        "product_description_zh": "适用于花园、禽舍、通风口和户外 DIY 防护项目；裁切前核对包装规格，并佩戴手套与护目镜安装。",
        "shopping_questions": [
            {
                "question": "What mesh size and gauge is included?",
                "answer_basis": "Use the verified package specification; exact values are unresolved in fixture mode",
                "answer_zh": "以已确认包装规格为准；离线模式下具体数值待补",
            },
            {
                "question": "How should I cut and install it?",
                "answer_basis": "Use suitable wire cutters and fasteners with gloves and eye protection",
                "answer_zh": "使用合适钢丝钳和紧固件，并佩戴手套与护目镜",
            },
        ],
        "a_plus_modules": [
            {
                "module": "Use-Case Grid",
                "purpose": "Map verified applications to shopper intent",
                "content": "Coop, garden bed, vent, and DIY barrier scenes",
            }
        ],
        "keyword_intent_map": {
            "title": ["hardware cloth"],
            "item_highlights": ["galvanized welded mesh"],
            "bullets": ["chicken coop", "garden barrier", "cut to fit"],
            "search_terms": ["rabbit hutch", "tree guard", "crawl space vent"],
        },
        "category_recommendations": [
            {
                "path": "Patio, Lawn & Garden > Fencing > Hardware Cloth",
                "node_id_path": "",
                "basis": "Fixture category-language hypothesis",
                "verification": "manual_validation_required",
            }
        ],
        "claim_evidence_map": [
            {
                "claim": "Galvanized welded mesh",
                "source": "user brief material/finish",
                "status": "verify_before_upload",
            },
            {
                "claim": "Exact mesh opening and gauge",
                "source": "missing from fixture brief",
                "status": "unresolved",
            },
        ],
        "attribute_checklist": ["mesh opening", "wire gauge", "roll width", "roll length", "material and finish"],
        "compliance_notes": ["Verify live category validator", "Human review required for safety-sensitive claims"],
        "unresolved": ["exact mesh opening", "exact gauge", "exact roll dimensions"],
        "notes_zh": "Mock 成稿；上架前用真实规格替换待补项。",
    }
