# Listing Creation Design

## Direction

Conversational staged creation workbench: collect brief, research/audience, product interpretation,
optional competitor analysis, five selling points, then Title + Item Highlights + bullets + search
terms under post-2026-07-27 field limits.

## Pipeline (approval gates)

```text
BRIEF + 事实台账
  → AUDIENCE（受众与市场审批）
  → PRODUCT（产品解读审批）
  → COMPETITOR?（竞品分析审批，可跳过）
  → SELLING_POINTS（五大卖点审批）
  → KEYWORDS（关键词与意图库审批）
  → FINAL_COPY（最终文案审批；BLOCK 不可过门）
  → IMAGE_HANDOFF（是否主图+7辅图 → amazon-image-design）
  → COMPLETED
```

User messages: free-text brief, `认可`, `跳过竞品`, `直接输出` (仍过证据门),
`需要图片` / `不需要图片`.

## Evidence hierarchy (high wins)

1. Amazon 官方规则  
2. 法律和安全要求  
3. 已确认产品资料  
4. 品牌后台数据  
5. SellerSprite 等第三方（仅市场上下文）  
6. 竞品页面 / 评论 / Q&A  
7. 定性假设（hypothesis）

Lower tiers cannot override higher facts. Unsourced numbers, certifications,
and performance claims are blocked from final copy (`authorize_copy_claims`).

## Hard gates

- Title plain ≤75 (non-media)
- Item Highlights ≤125
- Search Terms ≤250 UTF-8 bytes
- `lint_listing.py` PASS/WARN/BLOCK
- Evidence claim authorization on final copy
- No invented facts; gaps → `待补`

## MCP

Self-contained under `amazon_create/mcp`. Fixture mock by default; live endpoints when keys set.
