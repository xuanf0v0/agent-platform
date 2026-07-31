"""Deterministic offline LLM for staged creation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
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
        _ = kwargs
        if "维护界面侧栏的已确认产品事实" in system:
            return json.dumps({"facts": _confirmed_facts(user)}, ensure_ascii=False)
        if "可用工具由以下 JSON 接口提供" in system:
            return '{"tool":"none","asin":"","marketplace":"","product_name":"","specs":""}'
        if "完整理解全部会话历史" in system:
            latest = user.rsplit("USER: ", maxsplit=1)[-1].split("\n\n", maxsplit=1)[0]
            return f"我理解你的意思：{latest}"
        if "FACT_REASONING_V1" in system:
            return json.dumps(_fact_reasoning_payload(user), ensure_ascii=False)
        payload = _stage_payload(user)
        return json.dumps(payload, ensure_ascii=False)

    def stream(self, system: str, user: str, **kwargs: object) -> Iterator[str]:
        """Yield deterministic chunks while retaining mock call accounting."""
        response = self.complete(system, user, **kwargs)
        for index in range(0, len(response), 48):
            yield response[index : index + 48]

    def select_tool(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        _ = (system, user, tools)
        self._call_count += 1
        return None


def _confirmed_facts(user: str) -> list[dict[str, str]]:
    conversation = user.split("CONVERSATION:\n", maxsplit=1)[-1].split(
        "\n\nCURRENT_CONFIRMED_FACTS:", maxsplit=1
    )[0]
    patterns = (
        ("asin", "产品 ASIN", "基础信息", r"(?im)(?:产品\s*)?ASIN\s*[:：=]?\s*([A-Z0-9]{10})\b"),
        ("marketplace", "目标站点", "基础信息", r"(?im)(?:站点|目标站点)\s*[:：=]\s*([A-Z]{2,3})\b"),
        ("material", "材质", "规格参数", r"(?im)材质\s*[:：=]\s*([^\n,;，；]+)"),
        ("size", "产品尺寸", "规格参数", r"(?im)(?:产品)?尺寸\s*[:：=]\s*([^\n,;，；]+)"),
        ("count", "数量", "包装信息", r"(?im)数量\s*[:：=]\s*([^\n,;，；]+)"),
    )
    facts: list[dict[str, str]] = []
    for key, label, group, pattern in patterns:
        matches = list(re.finditer(pattern, conversation))
        if not matches:
            continue
        match = matches[-1]
        facts.append(
            {
                "key": key,
                "label": label,
                "value": match.group(1).strip(),
                "group": group,
                "source_quote": match.group(0).strip(),
            }
        )
    return facts


def _fact_reasoning_payload(user: str) -> dict[str, Any]:
    source = user.split("SOURCE:\n", maxsplit=1)[-1].split("\nRULES:\n", maxsplit=1)[0]
    facts: list[dict[str, Any]] = []
    known: set[str] = set()
    for match in re.finditer(
        r"(?im)^\s*(material|材质|size|尺寸|count|数量|finish|表面处理)\s*[:：=]\s*([^\n,;，；]+)",
        source,
    ):
        raw_key, value = match.group(1), match.group(2).strip()
        key_map = {"材质": "material", "尺寸": "size", "数量": "count", "表面处理": "finish"}
        key = key_map.get(raw_key.casefold(), raw_key.casefold())
        known.add(key)
        facts.append(
            {
                "key": key,
                "label_zh": {"material": "材质", "size": "尺寸", "count": "数量", "finish": "表面处理"}.get(key, key),
                "value": value,
                "group": "规格参数",
                "required": True,
                "question_zh": f"请确认{key}",
                "rationale_zh": "fixture category requirement",
                "source_quote": value,
            }
        )
    for key, label in (("material", "材质"), ("size", "尺寸")):
        if key not in known:
            facts.append(
                {
                    "key": key,
                    "label_zh": label,
                    "value": "",
                    "group": "规格参数",
                    "required": True,
                    "question_zh": f"请提供{label}",
                    "rationale_zh": "fixture category requirement",
                    "source_quote": "",
                }
            )
    return {"facts": facts}


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
            "category_market_overview": [
                {
                    "dimension": "类目成熟度",
                    "market_situation": "方向性估算：成熟且同质化较高",
                    "listing_impact": "优先表达已确认规格和真实用途",
                }
            ],
            "audience_profiles": [
                {
                    "audience_type": "核心受众",
                    "typical_traits": "DIY homeowners",
                    "estimated_share": "40%-55%（方向性估算）",
                    "core_needs": "reliable barrier material",
                    "scenarios": ["garden fence", "chicken coop"],
                    "purchase_barriers": "unclear dimensions",
                    "estimate_basis": "category language hypothesis",
                }
            ],
            "purchase_motivations": [
                {
                    "rank": index,
                    "motivation": f"purchase motivation {index}",
                    "need": "complete a practical task",
                    "importance_or_share": "方向性估算",
                    "placement": "Bullet Points",
                }
                for index in range(1, 11)
            ],
            "shopper_concerns": [
                {
                    "rank": index,
                    "question": f"shopper concern {index}",
                    "importance": "高",
                    "impact_if_unclear": "purchase hesitation",
                    "placement": "Title" if index == 1 else "Bullet Points",
                }
                for index in range(1, 11)
            ],
            "positive_reviews": [
                {
                    "rank": 1,
                    "content": "easy to use",
                    "need": "efficient installation",
                    "frequency_or_importance": "方向性估算",
                    "convertible_selling_point": "practical setup",
                }
            ],
            "negative_reviews": [
                {
                    "rank": 1,
                    "content": "dimensions misunderstood",
                    "root_cause": "listing ambiguity",
                    "frequency_or_severity": "方向性估算",
                    "handling": "state verified dimensions clearly",
                }
            ],
            "market_conclusion": {
                "core_audience": "DIY homeowners",
                "core_motivation": "complete barrier projects",
                "top_five_questions": ["identity", "size", "material", "installation", "contents"],
                "conversion_direction": "verified specs and practical use",
                "largest_pain": "unclear fit",
                "competitor_gap": "weak expectation management",
                "listing_priority": "identity and verified specifications",
            },
            "data_notes": ["Fixture mode; all shares are 方向性估算 without a live sample"],
            "notes_zh": "无实时评论数据时为定性假设，已标注 hypothesis。",
        }
    if "stage:product" in text or "product interpretation" in text:
        return {
            "parameter_analysis": [
                {
                    "product_parameter_or_function": "mesh size",
                    "meaning": "opening dimension",
                    "consumer_need": "fit for intended barrier task",
                    "audience": "DIY homeowners",
                    "scenario": "garden barrier",
                    "selling_point_value": "core purchase condition",
                    "recommended_location": "Title or Bullet",
                    "classification": "待确认 if absent",
                }
            ],
            "consistency_checks": [
                {
                    "check": "product vs package dimensions",
                    "result": "待确认",
                    "impact": "return risk",
                    "required_action": "confirm source specification",
                }
            ],
            "product_conclusion": {
                "core_conditions": ["verified size"],
                "basic_configuration": ["category-standard form"],
                "differentiators": ["待确认"],
                "placement_decisions": {"title": ["identity", "size"]},
            },
            "notes_zh": "按参数映射意图；缺失规格保持待补。",
        }
    if "stage:competitor" in text or "competitor analysis" in text:
        return {
            "selection_basis": ["direct", "leading", "same-price", "same-spec", "differentiated"],
            "basic_comparison": [],
            "feature_comparison": [],
            "title_analysis": [],
            "bullet_analysis": [],
            "promise_review_consistency": [],
            "competitor_conclusion": {
                "common_selling_points": [],
                "omitted_needs": [],
                "product_advantages": ["待确认"],
                "weaknesses": ["待确认"],
                "useful_structure": "identity then verified attributes",
                "avoid": "keyword stuffing",
                "positioning": "evidence-led",
            },
            "notes_zh": "未提供竞品 ASIN 时仅输出机会假设。",
        }
    if "stage:selling_points" in text or "selling points" in text:
        return {
            "selling_points": [
                {
                    "priority": 1,
                    "core_selling_point": "Core functional value",
                    "consumer_need": "complete the main task",
                    "product_evidence": "verified product facts or 待确认",
                    "competitor_difference": "evidence-led positioning",
                    "recommended_location": "Title and Bullet 1",
                },
                {
                    "priority": 2,
                    "core_selling_point": "Material or structure value",
                    "consumer_need": "durable use",
                    "product_evidence": "verified material or 待确认",
                    "competitor_difference": "待确认",
                    "recommended_location": "Bullet 2",
                },
                {
                    "priority": 3,
                    "core_selling_point": "Pain-point solution",
                    "consumer_need": "reduce task friction",
                    "product_evidence": "verified function or 待确认",
                    "competitor_difference": "clear benefit",
                    "recommended_location": "Bullet 3",
                },
                {
                    "priority": 4,
                    "core_selling_point": "Audience and scenario value",
                    "consumer_need": "know where it fits",
                    "product_evidence": "verified use case",
                    "competitor_difference": "specific scenario",
                    "recommended_location": "Bullet 4",
                },
                {
                    "priority": 5,
                    "core_selling_point": "Multi-use value",
                    "consumer_need": "broader application",
                    "product_evidence": "verified compatible uses",
                    "competitor_difference": "versatile positioning",
                    "recommended_location": "Bullet 5",
                },
            ],
            "notes_zh": "五大卖点按意图排序，缺规格处已标待补。",
        }
    if "stage:keywords" in text:
        return {
            "keyword_categories": {
                "core_category": ["hardware cloth"],
                "use": ["garden barrier"],
                "irrelevant": [],
                "prohibited_or_infringing": [],
            },
            "top20_roots": [
                {
                    "rank": index,
                    "root": f"root{index}",
                    "type": "category" if index == 1 else "semantic",
                    "search_intent": "purchase research",
                    "relevance": 10 - min(index // 3, 5),
                    "recommended_location": "Title" if index <= 3 else "Search Terms",
                }
                for index in range(1, 21)
            ],
            "top20_keywords": [
                {
                    "rank": index,
                    "keyword": f"product keyword {index}",
                    "search_intent": "commercial",
                    "traffic_level": "方向性估算",
                    "conversion_intent": "high" if index <= 5 else "medium",
                    "product_match": 10 - min(index // 4, 5),
                    "recommended_location": "Title" if index <= 3 else "Bullet",
                }
                for index in range(1, 21)
            ],
            "keyword_allocation": [
                {
                    "keyword": "hardware cloth",
                    "type": "core category",
                    "Title": True,
                    "Item Highlights": False,
                    "Bullet": True,
                    "Description": True,
                    "Search Terms": False,
                }
            ],
            "notes_zh": "关键词与意图库（第三方数据仅作市场上下文）。",
        }
    # Final copy default (stage:final_copy or unspecified)
    title_variants = [
        {
            "code": "A",
            "strategy_zh": "SEO与转化平衡版",
            "title": "Brand Hardware Cloth Welded Wire Mesh Roll for Garden and Coop Use",
            "title_zh": "品牌焊接铁丝网卷，适用于花园与鸡舍",
            "title_chars": 70,
            "primary_keywords": ["hardware cloth", "welded wire mesh"],
            "item_highlights": "Galvanized welded mesh for garden beds, poultry runs, and practical DIY barriers",
            "item_highlights_zh": "镀锌焊接网，适用于花坛、禽舍与实用户外防护",
            "item_highlights_chars": 82,
        },
        {
            "code": "B",
            "strategy_zh": "突出核心差异化版",
            "title": "Brand Welded Wire Mesh Hardware Cloth for Outdoor Barrier Projects",
            "title_zh": "品牌户外防护工程焊接铁丝网",
            "title_chars": 68,
            "primary_keywords": ["welded wire mesh", "hardware cloth"],
            "item_highlights": "Project-ready mesh supports coop panels, garden protection, vents, and custom guards",
            "item_highlights_zh": "工程网材适用于禽舍板、花园防护、通风口与定制护栏",
            "item_highlights_chars": 86,
        },
        {
            "code": "C",
            "strategy_zh": "简洁高可读性版",
            "title": "Brand Hardware Cloth Mesh Roll for Garden, Coop, and DIY Barriers",
            "title_zh": "品牌铁丝网卷，适用于花园、禽舍和DIY防护",
            "title_chars": 67,
            "primary_keywords": ["hardware cloth", "mesh roll"],
            "item_highlights": "Welded mesh roll for straightforward outdoor protection and custom-fit projects",
            "item_highlights_zh": "焊接网卷适合直接的户外防护和定制项目",
            "item_highlights_chars": 76,
        },
    ]
    bullets = [
        {
            "text": (
                "Practical Barrier Coverage: Built around verified product specifications to support "
                "garden, coop, and household barrier projects with a clear fit for the task at hand"
            ),
            "text_zh": "实用防护覆盖：基于已确认产品规格，支持花园、禽舍和家用防护项目",
            "purchase_intent_zh": "完成主要防护任务",
            "covered_keywords": ["hardware cloth", "barrier mesh"],
            "chars": 169,
        },
        {
            "text": (
                "Reliable Welded Structure: The verified material and construction create a useful "
                "foundation for everyday outdoor projects while keeping setup and placement straightforward"
            ),
            "text_zh": "可靠焊接结构：已确认材质与结构为日常户外项目提供实用基础",
            "purchase_intent_zh": "关注材质和结构",
            "covered_keywords": ["welded wire mesh"],
            "chars": 172,
        },
        {
            "text": (
                "Clear Project Matching: Verified dimensions and configuration help shoppers compare "
                "the mesh with their intended opening or frame before beginning a custom barrier project"
            ),
            "text_zh": "清晰项目匹配：已确认尺寸和配置帮助消费者在施工前判断适配性",
            "purchase_intent_zh": "降低尺寸不匹配风险",
            "covered_keywords": ["mesh roll", "custom barrier"],
            "chars": 174,
        },
        {
            "text": (
                "Useful Outdoor Scenarios: Apply the verified product format to garden beds, poultry "
                "runs, vent covers, or similar DIY spaces where a fitted physical barrier is needed"
            ),
            "text_zh": "实用户外场景：适用于花坛、禽舍、通风口和类似DIY空间",
            "purchase_intent_zh": "确认典型场景",
            "covered_keywords": ["garden barrier", "poultry run"],
            "chars": 166,
        },
        {
            "text": (
                "Flexible Project Planning: Use the confirmed size, package contents, and compatible "
                "applications to plan custom sections without repeating the same solution across every space"
            ),
            "text_zh": "灵活项目规划：结合确认尺寸、包装内容和兼容用途规划定制区域",
            "purchase_intent_zh": "多用途和拓展应用",
            "covered_keywords": ["DIY mesh", "custom sections"],
            "chars": 173,
        },
    ]
    return {
        "title_variants": title_variants,
        "recommended_variant": "A",
        "title": title_variants[0]["title"],
        "title_zh": "品牌铁丝网焊接卷材",
        "item_highlights": title_variants[0]["item_highlights"],
        "item_highlights_zh": "镀锌焊接网，适用于鸡舍、花坛与户外 DIY 防护",
        "bullets": bullets,
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
        "product_description_chars": 319,
        "shopping_questions": [
            {
                "question": "What mesh size and gauge is included?",
                "answer_basis": "Use the verified package specification; exact values are unresolved in fixture mode",
                "answer_zh": "以已确认包装规格为准；离线模式下具体数值待补",
                "listing_answered": True,
                "location": "Product Description",
                "clarity": "部分清晰",
                "missing_information": "exact values",
            },
            {
                "question": "How should I cut and install it?",
                "answer_basis": "Use suitable wire cutters and fasteners with gloves and eye protection",
                "answer_zh": "使用合适钢丝钳和紧固件，并佩戴手套与护目镜",
                "listing_answered": True,
                "location": "Product Description",
                "clarity": "清晰",
                "missing_information": "",
            },
        ] + [
            {
                "question": f"Shopper question {index}?",
                "answer_basis": "verified product facts only",
                "answer_zh": "仅依据已确认产品事实回答",
                "listing_answered": False,
                "location": "Q&A",
                "clarity": "待确认",
                "missing_information": "待确认",
            }
            for index in range(3, 11)
        ],
        "compliance_risks": [
            {
                "risk_type": "未经证实声明",
                "issue": "认证和测试必须有产品证据",
                "level": "高",
                "recommended_location": "合规检查",
                "needs_confirmation": True,
            }
        ],
        "return_risks": [
            {
                "risk_type": "尺寸误解",
                "issue": "产品尺寸与包装尺寸必须区分",
                "level": "中",
                "recommended_location": "Product Description",
                "needs_confirmation": True,
            }
        ],
        "creation_logic_zh": "以已确认事实为边界，按购买决策优先级分配关键词和五个独立卖点。",
        "final_report": {},
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
