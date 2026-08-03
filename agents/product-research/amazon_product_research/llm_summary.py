"""Evidence-bounded LLM summary; deterministic data remains authoritative."""

from __future__ import annotations

import json

from openai import OpenAI

from .config import Settings
from .models import ResearchResult


def summarize(settings: Settings, result: ResearchResult) -> list[str] | None:
    key = settings.openai_api_key.get_secret_value()
    if not key or not result.candidates:
        return None
    payload = {
        "decision": result.decision,
        "candidates": [
            {
                "title": row.title,
                "asin": row.asin,
                "price_usd": row.price_usd,
                "cost_usd": row.cost_usd,
                "margin_pct": row.estimated_margin_pct,
                "review_count": row.review_count,
                "score": row.score.model_dump(mode="json") if row.score else None,
            }
            for row in result.candidates[:10]
        ],
        "gaps": result.gaps,
    }
    client = OpenAI(api_key=key, base_url=settings.openai_api_base, timeout=45)
    response = client.chat.completions.create(
        model=settings.analysis_model,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 Amazon 选品分析师。只能解释输入 JSON 中已有的数据，禁止补造数字、规格、"
                    "认证或市场事实。输出严格 JSON 字符串数组，包含 3-5 条中文结论，每条按“数据→含义→行动”组织。"
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    content = response.choices[0].message.content or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    output = [str(item).strip()[:500] for item in parsed if str(item).strip()]
    return output[:5] or None
