# Amazon Listing Creation Agent

从 0 到 1 创建 Amazon Listing，并由 Agent Manager 统一启动和管理。

- **默认审批门**：Brief/事实台账 → 受众 → 产品解读 → 竞品 → 五大卖点 → 关键词意图库 → 最终文案 → 图片组分析 → 主图+7辅图方案
- **证据等级**：Amazon 官方 > 法律安全 > 已确认产品资料 > 品牌后台 > 第三方 MCP > 竞品/评论 > 假设；低等级不能覆盖高等级；无来源数字/认证/性能不得进终稿
- **完整输出**：Title、Item Highlights、5 Bullets、Description、Search Terms、Alexa 问题覆盖、A+/EBC、关键词意图图、类目候选、宣称证据表、合规提示
- **规则路由**：运行时强制加载政策基线、创建流程、COSMO/Alexa 规则，并按产品类型加载 `Downloads/c` 对应品类 reference
- **研究路由**：按目标站点请求市场数据；产品和竞品 ASIN 独立调研；SellerSprite 类目候选始终标记为待 Amazon 页面/后台人工验证
- **图片流程**：优先使用产品/竞品 ASIN 研究图片组；无法获取时才请求上传，分析确认后生成 1 主图 + 7 辅图及八维评分
- **敏感品类**：儿童、婴幼儿、食品、补剂、医疗、化妆品、健康、安全及电子认证相关产品必须人工终审
- **规则**：2026-07-27 后非 media Title ≤75、Item Highlights ≤125、Search Terms ≤250 UTF-8 bytes
- **MCP**：自 `listing-optimization-agent` **整包拷贝**至 `amazon_create/mcp`，本仓自维护

不依赖旁路安装 `amazon-copy`。

## Install

```bash
cd /Users/ypc/agent-manager/agents/listing-creation
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

从 Agent Manager 主界面启动 `Listing 创作 Agent`。React 页面和 Python API 由管理器统一运行。

启动前请配置 `.env`（见 `.env.example`）中的真实模型 API Key。真实市场调研还需至少一个 MCP Key；没有 MCP Key 时系统只输出明确标注的定性假设，不会使用演示数据冒充研究结果。

## CLI

```bash
amz-create fast --product "Hardware Cloth" --market US --specs "..." --live
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
## React Build

React + TypeScript SPA 复用现有 Python 创作流水线。修改页面后构建生产包：

```bash
cd web
npm install
npm run build
```
