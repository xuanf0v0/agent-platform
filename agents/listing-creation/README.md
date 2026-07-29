# Amazon Listing Creation Agent

从 0 到 1 创建 Amazon Listing，并由 Agent Manager 统一启动和管理。

- **长提示词输入**：首轮可直接粘贴完整产品提示词、说明书和规格资料；Agent 会拆分提取基础信息与最多 128 条原子事实
- **全程对话**：首轮事实以一份完整摘要统一确认；缺失、歧义、冲突、阶段认可和修改意见都通过聊天处理，侧栏仅持续展示事实、问题、规则、研究和进度
- **分块审批门**：事实摘要 → 市场与受众 → 产品解读 → 竞品 → 五大卖点 → 关键词 → Listing；每个阶段按小块讨论并保持硬顺序
- **受控 ReAct**：每次需要生成或切换阶段时，计划器只可选择市场研究、ASIN 公开快照或继续当前阶段；最多执行两项白名单工具，并在侧栏保留动作与观察记录，不展示思维链
- **证据等级**：Amazon 官方 > 法律安全 > 已确认产品资料 > 品牌后台 > 第三方 MCP > 竞品/评论 > 假设；低等级不能覆盖高等级；无来源数字/认证/性能不得进终稿
- **完整输出**：二十段研究与创作报告、3 套 Title + Item Highlights、最终推荐稿、5 Bullets、Description、Search Terms、Rufus 十问、合规与退货风险及独立可上传版本
- **规则路由**：运行时强制加载政策基线、创建流程、COSMO/Alexa 规则，并按产品类型加载 `Downloads/c` 对应品类 reference
- **研究路由**：按目标站点请求市场数据；产品和竞品 ASIN 独立调研；SellerSprite 类目候选始终标记为待 Amazon 页面/后台人工验证
- **身份提取**：产品 ASIN 与目标站点只接受明确标签；`核心市场词`、报告中的 `US` 或未标注子体编号不会被误当成站点/产品 ASIN
- **ASIN 连通**：确认产品 ASIN 和站点后，在市场/竞品等相关阶段按需调用 SellerSprite `asin_detail`；公开快照只作为第三方研究，不会自动覆盖已确认产品事实
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

从 Agent Manager 主界面启动 `Listing 创作 Agent`。管理器直接启动 Streamlit 页面。

对话、提问清单、已确认事实和流程 checkpoint 默认保存在 `.data/listing_creation.sqlite3`。修改事实并确认新摘要后，系统保留不受影响的已批准阶段，并从最早受影响阶段自动重新开始。

启动前请配置 `.env`（见 `.env.example`）中的真实模型 API Key。真实市场调研还需至少一个 MCP Key；没有 MCP Key 时系统只输出明确标注的定性假设，不会使用演示数据冒充研究结果。SellerSprite、Sorftime、SIF 及两个可选写作 MCP 的配置项与优化 Agent 保持一致。

## CLI（开发辅助）

```bash
amz-create fast --product "Hardware Cloth" --market US --specs "..." --live
```

CLI 无人工确认界面，因此输出始终按不可上传草稿处理；生产创作请使用 Streamlit。

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
