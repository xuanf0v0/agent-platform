# Amazon Listing Creation Agent

独立仓库：从 0 到 1 创建 Amazon Listing（Title + Item Highlights + 5 Bullets + Search Terms）。

- **默认审批门**：Brief/事实台账 → 受众 → 产品解读 → 竞品 → 五大卖点 → 关键词意图库 → 最终文案 → 主图+7辅图交接
- **证据等级**：Amazon 官方 > 法律安全 > 已确认产品资料 > 品牌后台 > 第三方 MCP > 竞品/评论 > 假设；低等级不能覆盖高等级；无来源数字/认证/性能不得进终稿
- **入口**：`streamlit run amazon_create/ui/app.py`
- **规则**：2026-07-27 后非 media Title ≤75、Item Highlights ≤125、Search Terms ≤250 UTF-8 bytes
- **MCP**：自 `listing-optimization-agent` **整包拷贝**至 `amazon_create/mcp`，本仓自维护

不依赖旁路安装 `amazon-copy`。

## Install

```bash
cd /Users/ypc/listing-creation-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run UI

```bash
streamlit run amazon_create/ui/app.py
```

默认 `MOCK=true` 可离线演示。真实 LLM 时配置 `.env`（见 `.env.example`）。

## CLI

```bash
amz-create fast --product "Hardware Cloth" --market US --specs "..." --mock
```

## Resources

- `amazon_create/resources/amazon-listing-creation/` — 分阶段创作 skill
- `amazon_create/resources/amazon-listing-policy-and-semantic-copy/` — 政策 + lint
- `amazon_create/resources/amazon-cosmo-rufus-copywriting/` — COSMO/Alexa 文案与品类 references

来源：`~/Downloads/c`（2026-07-28 包）。

## MCP provenance

Vendored from `listing-optimization-agent/amazon_copy/mcp` with package rename
`amazon_copy` → `amazon_create`. Third-party MCP data is market context only and
cannot authorize private product/safety claims.

## Boundary vs optimization agent

| | Creation (this repo) | Optimization |
|--|----------------------|--------------|
| Input | Product brief / specs | Existing listing text |
| Flow | Staged approvals | One-box rewrite / studio |
| Output | New listing fields | Optimized paste-ready copy |

## Tests

```bash
pytest -q
```
# React Application

The primary UI is a React + TypeScript SPA backed by the existing Python creation pipeline.
Build and run the complete packaged application with:

```bash
cd web
npm install
npm run start
```

Open `http://127.0.0.1:8100`. The server hosts both the JSON API and production frontend.
