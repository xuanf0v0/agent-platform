# Amazon Listing Creation Agent

从 0 到 1 创建 Amazon Listing，并由 Agent Manager 统一启动和管理。

- **提示词驱动**：完整创作工作流只作为系统提示词交给模型，不再由程序拆解为固定字段、阶段或确认门禁
- **自由对话**：模型结合全部消息历史自主回答、追问、研究、修改和创作，不使用程序预设回复
- **已确认事实侧栏**：每轮由 LLM 从用户明确提供或确认的内容重建事实快照；规则文本、竞品、MCP 和助手推测不会自动记为产品事实
- **原生工具选择**：模型按上下文自主选择 SellerSprite/SIF 市场研究或 ASIN 公开快照；第三方结果作为不可信研究上下文交回模型判断
- **真实流式输出**：用户消息即时显示，等待期间显示响应状态，模型文本按原始增量直接输出
- **LangGraph 持久化**：LangGraph 只保存消息、会话标题和待处理消息，不参与业务决策
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

从 Agent Manager 主界面启动 `Listing 创作 Agent`。管理器启动 FastAPI 服务，Vue 管理界面提供对话页面。

对话 checkpoint 默认保存在 `.data/listing_creation.sqlite3`。

启动前请配置 `.env`（见 `.env.example`）中的真实模型 API Key。真实市场调研还需至少一个 MCP Key；没有 MCP Key 时系统只输出明确标注的定性假设，不会使用演示数据冒充研究结果。SellerSprite、Sorftime、SIF 及两个可选写作 MCP 的配置项与优化 Agent 保持一致。

## CLI（开发辅助）

```bash
amz-create fast --product "Hardware Cloth" --market US --specs "..." --live
```

CLI 保留为旧流水线的开发辅助入口；生产创作请使用 Agent Manager 中的对话页面。

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
| Flow | Prompt-driven conversation | Diagnose, approve, optimize |
| Output | New listing fields | Optimized paste-ready copy |

## Tests

```bash
pytest -q
```
