---
name: amazon-cosmo-rufus-copywriting
description: "Use when the user says 文案创作 or asks to create/rewrite Amazon listing copy with COSMO/Rufus intent-first logic. Follow staged workflow with approval gates unless the user explicitly asks to skip."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [amazon, listing, copywriting, cosmo, rufus, ecommerce]
    related_skills: [amazon-listing-creation, amazon-listing-optimization, walmart-marketplace-listing-copywriting]
---

# Amazon COSMO / Alexa for Shopping（原 Rufus）文案创作

## Overview

当用户输入“文案创作”时，默认启动本流程。当前产品名称使用 Alexa for Shopping，Rufus 仅作为旧名和触发词。

开始前必须加载 `amazon-listing-policy-and-semantic-copy`。共享 Skill 的 2026-07-27 后政策、证据分级、评论/变体红线和校验规则覆盖本文件中的旧 SOP 冲突。

核心原则：

- 从“关键词堆叠”升级为“搜索意图优先”。
- 每个卖点都要对应一个明确购买意图、痛点、场景、产品参数和可验证收益。
- 文案要服务搜索相关性、COSMO 语义/意图理解和 Alexa for Shopping 自然语言问答提取，但不承诺排名或推荐。
- 所有数字、规格、材质、认证、兼容性、质保、功效都必须来自用户 brief、可靠页面或工具数据；缺失则标注“待补”，不得杜撰。
- 用户偏好分阶段审批：市场/受众分析、产品解读、竞品分析、卖点提炼、最终文案前都要询问是否认可，除非用户明确要求直接输出。

## When to Use

Use this skill when:

- 用户输入“文案创作”。
- 用户要求重新输出更符合 COSMO / Rufus 算法的 Amazon listing。
- 用户要从 0 到 1 创建 Amazon 标题、五点、描述、后台词、Q&A、A+ 架构。
- 用户提供产品名、ASIN、竞品 ASIN、关键词库、规格参数或旧文案，让你重写 listing。
- 用户强调“用户搜索意图”“COSMO”“Rufus”“语义化”“上下文相关词汇”“AI购物助手可回答”。

Do not use this as the primary workflow when:

- 用户只要诊断/优化已上线 Amazon listing 且没有要求从头创作；优先用 `amazon-listing-optimization`，但可借用本 skill 的 COSMO/Rufus 检查维度。
- 用户明确要求 Walmart US / Walmart Marketplace 文案；不要套用 Amazon 的 75 字符标题、Item Highlights、COSMO/Rufus、A+ 或后台词结构。改用 `walmart-marketplace-listing-copywriting`，按 Walmart 的 Product Title + Key Features + Product Description 输出。
- 用户只要纯翻译；需要先确认是否按本地化 listing 创作重写，而非逐句翻译。

## Trigger Behavior for “文案创作”

当用户只输入“文案创作”而没有其他信息时，不要直接写稿。先索取最小必要 brief：

| 需要信息 | 说明 |
|---|---|
| 产品名称 / ASIN | 如 Hardware Cloth / B0FR8X1S8Y |
| 目标市场 | US / UK / DE / FR / IT / ES 等 |
| 产品规格参数 | 尺寸、材质、数量、功能、适用对象、认证、包装清单 |
| 原标题与五点 | 如是重写/优化，请提供旧版 |
| 竞品 ASIN 或竞品文案 | 如有，用于对标；没有也可以继续 |
| TOP关键词 / 词根 | 如没有，用 SellerSprite 调研 |
| 品牌调性与禁用表达 | 如专业、亲和、高端、简洁等 |

完成标准：已拿到产品名称和目标市场；如缺规格，后续所有涉及规格处必须写“待补”。

## 2026 Amazon Title + Item Highlights Rule Update

Source learned from Amazon Seller Forums thread `145b6d0f-999c-4555-896c-c694bda2e470` (“Updates to improve your product titles begin on July 27”, updated Jun 10, 2026):

- Starting **July 27, 2026**, product titles in **all categories except media** must be **75 characters or less including spaces**.
- Amazon introduced **Item Highlights**: an additional **125 characters** for materials, recommended use cases, and comparison details. Item Highlights are **searchable** and visible with titles in search results and on detail pages.
- Title strategy must shift from long keyword-heavy titles to a **75-character mobile-first title + 125-character searchable Item Highlights** structure.
- If titles remain over 75 characters after July 27, Amazon may gradually update them to AI recommendations. Brand owners get a **14-day review window** in Review Listings Changes before implementation.
- 直接按 2026-07-27 后规则写；不输出 legacy 长标题分支，media 类目单独查当前规则。

Operational implication for this skill: put only the highest-value information in Title; move secondary materials, use cases, compatibility, and extra semantic keywords into Item Highlights, bullets, description, A+, and backend search terms.

## Staged Workflow with Approval Gates

### Step 1 — Brief Intake

收集并整理用户提供的信息：产品名、站点、语言、规格、卖点、旧文案、竞品、关键词、合规限制。

输出一个 brief 表格，并标出：

- 已确认信息
- 缺失信息
- 不可杜撰信息
- 可能涉及合规审核的信息

完成标准：用户确认 brief，或明确允许基于现有信息继续。

### Step 2 — Market / Audience / Intent Research

输出目标市场分析，必须包含：

1. 有数据支持的目标受众与使用场景。
2. 有数据支持的购买动机。
3. 有数据支持的用户问题。
4. 有真实评论样本支持的好评点与差评点。
5. COSMO 意图层：核心需求、场景需求、问题/解决方案需求、属性规格需求、兼容/安装/清洁/安全需求。

只有在拥有可引用数据集和分母时才能给百分比。无法获取实时数据时，输出不带百分比的定性假设并标注 `hypothesis`；禁止虚构“方向性占比”。

完成标准：用表格输出并询问“是否认可，认可后进入产品解读”。

### Step 3 — Product-Spec Interpretation

先解释该品类买家通常如何比较产品，再解读用户产品规格。

必须映射：

| 产品参数/功能 | 买家关心点 | 对应购买意图 | 可写入文案的安全表达 | 缺失/风险 |
|---|---|---|---|---|

从多个维度解释：

- 核心规格
- 材质/工艺
- 使用场景
- 质量信号
- 安装/安全/清洁/维护
- 与竞品对比时有意义的差异点

完成标准：用户认可产品解读后，进入竞品分析；用户不提供竞品时，可进入卖点提炼。

### Step 4 — Competitor Analysis

如用户提供竞品 ASIN，用 SellerSprite / Amazon 页面 / 已给文案做分析。不要抄袭竞品文案，只参考结构和角度。

输出：

1. 竞品基础信息：品牌、价格、评分、评论数、BSR、核心规格。
2. 标题结构对比：核心词顺序、规格位置、场景词、差异化词。
3. 五点顺序对比：每条在讲什么购买意图。
4. 竞品优势/弱点：参数、文案、场景、合规风险。
5. 我方机会：哪些词、场景、痛点、证明点可以超越竞品。

完成标准：输出对比表，并询问是否认可，认可后进入卖点提炼。

### Step 5 — Selling-Point Extraction

按重要性提炼 5 个卖点。每个卖点必须包含：

| 排名 | 卖点 | 用户痛点/意图 | 产品依据 | 推荐关键词/语义词 | 合规表达 |
|---|---|---|---|---|---|

推荐顺序：

1. 第一卖点：最强购买理由，不要用泛泛的 “Multi-use” 开头。
2. 第二卖点：解决高频痛点或高转化场景。
3. 第三卖点：材质/耐用/安全/信任证明。
4. 第四卖点：规格/尺寸/兼容/场景覆盖。
5. 第五卖点：安装、使用、维护、风险降低或服务保障。

完成标准：询问用户是否认可五大卖点，认可后进入关键词与文案。

### Step 6 — Keyword + Intent Library

先建库，再写文案。不要直接写。

输出四层词库：

1. 数据支持的关键词：核心词、长尾词及可核验的购买率、搜索量、PPC、标题密度、用途建议。
2. 相关词根：root/stem、对应意图、布局位置；不设固定数量。
3. COSMO 语义词：场景词、问题词、属性词、对象词、解决方案词、互补用途词。
4. Alexa for Shopping（原 Rufus）问答词：买家会问的问题，如 who/when/where/how/what included/fit/clean/install/compare。

数据优先级：

1. SellerSprite 对应站点母语数据。
2. Amazon 搜索栏建议词、Related searches。
3. 竞品标题/五点/Q&A/Review 高频表达。
4. 产品 brief 中的真实规格。

完成标准：词库清晰分层，标注哪些进标题、Item Highlights、五点、描述、后台词、Q&A。

### Step 7 — Final Copywriting

根据已确认卖点和词库输出：

- Title (default **≤75 characters including spaces** for non-media categories)
- Item Highlights (up to **125 searchable characters** for materials/use cases/comparison details)
- 5 Bullet Points
- Product Description
- Search Terms
- Alexa for Shopping（原 Rufus）问答覆盖建议
- A+ / EBC 模块建议（如用户需要）
- 图片 brief（如用户需要）
- 中文翻译
- 关键词/意图埋入说明
- 合规风险提示

完成标准：文案输出后先询问用户是否确认文案。用户确认后，必须继续询问：“是否需要进入图片设计？我可以按主图+7张辅图做图片卖点规划、竞品图片分析和设计 brief。”

#### Title Rules

默认结构（2026 新规）：

`Brand + Core Keyword + One Critical Spec/Differentiator`

尺寸/适配敏感产品可改为：

`Brand + Size/Pack + Core Keyword + One Critical Attribute`

要求：

- **默认标题 ≤75 characters including spaces**（从 2026-07-27 起，Amazon 非 media 类目统一要求；当前新建文案也按此标准先写）。
- 标题只保留：品牌、最高价值核心词、决定点击/适配/误购风险的 1–2 个关键规格或差异点。
- 次级材料、用途、兼容场景、颜色、套装细节和长尾语义词，不再硬塞标题，优先移动到 **Item Highlights（125 characters）**、Bullet、Description、A+ 和 Search Terms。
- 核心关键词尽量靠前；但当尺寸决定购买/适配时，允许把真实尺寸、厚度、片数放在品牌后、核心词前，以降低误购和差评风险。
- US 站尺寸优先使用 inch/ft 表达；公制来源尺寸需准确换算并避免过度四舍五入造成“not true to size”争议。
- 不提供旧规长标题分支。
- 不堆促销词，不用 Best/Cheap/Free/100% Guaranteed。
- 不全部大写。
- 不使用竞品品牌。
- 尺寸、材质、数量必须真实。

#### Item Highlights Rules

Item Highlights 是标题后的新增可搜索补充字段，默认输出 1 条 **≤125 characters including spaces** 的英文版本（多站点按本地语言输出）。

For this user's US title-optimization workflow, when they follow a title request with `产品亮点`、`商品亮点`、`再写一个产品亮点` or similar wording, interpret it as **one Item Highlights line**, not five bullet points, unless they explicitly say `五点描述` or `Bullet Points`. Return the upload-ready English line, verified character count, and a concise Chinese reference. If they ask `再写一个`, provide a genuinely different angle rather than repeating the previous line.

写法：

`Material/Proof + Recommended Use Cases + Comparison Detail`

要求：

- 承接标题放不下但影响点击和比较的信息：材质、使用场景、适配对象、包含数量、颜色/套装、关键兼容信息。
- 语言必须像搜索结果里的短说明，不写完整五点，不堆砌逗号词串。
- 与 Title 形成互补：Title 抢核心点击，Item Highlights 补材料/用途/比较关键词。
- 同样禁止竞品品牌、促销词、无法证实的绝对化/功效宣称。
- 若类目/站点后台暂未开放该字段，仍输出为“Item Highlights 建议文案”，供运营在可用字段或 Search Query Performance/AI recommendations 场景中使用。

#### Bullet Rules

每条五点按：

`简短卖点标题 – 产品参数或证据 + 使用场景 + 买家收益`

要求：

- 每条围绕一个购买意图，不做无序功能堆砌。
- **五点标题要短、易扫读**：优先 2–4 个词，如 `TRUE SIZE FIRST`、`BRIGHTER GROWING`、`CUT & INSTALL`；避免冗长标题。
- **正文可以更长更有承接**：在平台/类目字符允许时，用较完整句子覆盖“谁用、用在哪、解决什么、怎么用、为什么值得买”，不要只写短功能清单。
- **规格敏感类目要尺寸前置**：板材、卷材、硬件、替换件等尺寸决定适配的产品，Title 和 Bullet 1 应把真实尺寸/数量放前面；US 站优先用 inch/ft，并可在必要处保留公制辅助。
- 优先写买家为什么需要它，再写产品怎么满足。
- 自然埋入关键词和词根；不要破坏可读性。
- 适当覆盖场景、对象、问题、解决方案和安装/维护信息。
- COSMO/购物助手文案要把真实场景、产品属性与买家收益讲清，而不是只罗列参数；不得加入促销式行动号召。
- 英文最终上传版不要保留 Markdown `**`。
- 若需要审核版，可加粗关键词；若用户要上传版，必须去掉 `**`。

#### Final Upload Formatting Rules

- 当用户要求“文字版”“输出文字版即可”“最终上传版”时，直接用纯文本分块输出 Title / Item Highlights / Bullet，不要放 Markdown 代码块，减少复制到表格或后台时的清理成本。
- 若用户要求可复制代码块，再使用代码块；否则默认 Feishu 普通文本格式。
- 用户要求“标题加埋词 / 五点丰富点多埋词”时，不要牺牲可读性硬堆词：Title 仍遵守 ≤75 characters；Bullet 只增加有证据的决策信息，不设置 200–300 字符或埋词数量目标。
- 五点小标题与正文的默认分隔符：最终上传版用普通半角 ` - `（如 `READY FOR ART - ...`），兼容 Excel 和 Amazon 后台；审核/展示稿可用 en dash ` – `，但不要默认用冒号。冒号偏说明文，` - ` 更像 Amazon 电商卖点格式且更易扫读。
- 英文 décor/decorations 用词：搜索词和五点具体用途优先用 `decorations`（如 `party decorations`, `classroom decorations`, `DIY decorations`）；只有表达整体风格/氛围时少量用 `décor`/`decor`（如 `event décor`, `seasonal décor`）。标题通常不放 decorations/décor。
- **UK 站尺寸与语气**：英国站文案尺寸默认先写公制，再用括号补英制，如 `18 x 13 cm (7 x 5 in)`、`30 cm (12 in)`；不要按 US 站先写 inches。非 media 标题仍必须 ≤75 characters。

#### UK Christmas Bows / Seasonal Décor Notes

When writing Amazon UK copy for pre-tied Christmas bows, velvet bows, wreath bows, garland bows, or bow-and-ribbon seasonal décor:

- Treat the likely category as **Home & Kitchen > Home Accessories > Seasonal Décor / Seasonal Decorations > Christmas > Bows & Ribbons** when the product is a finished pre-tied bow rather than ribbon roll material. SellerSprite/Amazon UK node observed for Bows & Ribbons: `11052681:376320011:3028681031:3028683031:3028686031`. Use this as a category recommendation, not a guaranteed backend browse node.
- Do not evaluate UK copy with US assumptions. UK copy should use British spelling where relevant (`colour`, `moulding` only if contextually right, but for bows prefer `shaping`), and should favour UK home décor scenes like `front door wreaths`, `staircases`, `banisters`, `mantelpieces`, `windows`, `gift boxes`, `home, office or shop displays`.
- For Christmas bow titles, the user dislikes titles that are too short. A stronger UK title can keep `18 Pack`, `Burgundy Velvet Christmas Bows`, `Gold Trim`, `Pre-Tied Double Layer`, and `Tree/Wreath/Garland` as long as it remains readable and not pure keyword stuffing.
- Avoid awkward competitor-style expressions: `Xmas` in main title, `Home Party Decor`, `Wreath Embellishments`, `Garland Adornments`, `sumptuous`, `ostentatious`, `winter door knockers`, and every-word title case in bullet body.
- Tone down over-marketing words unless proven: avoid repeated `premium`, `luxury`, `super value`, `splendour`, `worry free`, `ensures`, `perfectly sized`. Prefer grounded phrases such as `soft burgundy velvet`, `gold-trimmed edges`, `classic festive look`, `warm coordinated Christmas look`, `handy spare ties included`, `can be carefully stored and reused`.
- Good bullet order for this class: (1) pack count + pre-tied + size, (2) velvet/colour/gold trim/V-cut tails, (3) twist ties and spares if included, (4) UK home display locations, (5) Christmas & beyond seasonal use.

#### Product Description Rules

描述应补充五点未覆盖的信息：

1. 首段：产品定位 + 目标用户 + 核心用途。
2. 第二段：关键规格 + 场景 + 解决的问题。
3. 第三段：使用/安装/清洁/维护 + 安全提示。
4. 可加入 Note，但不得夸大。

#### Search Terms Rules

- 去掉标题/五点已充分覆盖的高频重复词，优先补同义词、变体、长尾和场景词。
- 不放竞品品牌、侵权词、促销词、夸大词。
- 默认控制在 **≤250 UTF-8 bytes**，并用脚本计数；目标站点/类目后台更严时服从更严规则。

#### Alexa for Shopping（原 Rufus）Q&A Rules

按真实买家问题与产品证据设计必要的自然语言问答覆盖，不设固定数量，围绕：

- Is it suitable for…?
- Can I use it for…?
- What size/material is it?
- How do I install/cut/clean it?
- What problem does it solve?
- What makes it different?

Q&A 只能基于真实参数，不得编造承诺。

评论相关建议不得引导好评、激励/返现换评、拦截差评、要求删改评论或使用变体聚评；中性邀评只走 Amazon `Request a Review`。

## Image Design Handoff After Copy Approval

当用户确认文案后，只做交接询问，不在本文案 skill 内展开图片设计 workflow：

> 文案已确认。是否需要进入图片设计？如果需要，我将切换到 `amazon-image-design`，按图片设计专用流程做主图 + 7 张辅图规划、ASIN 图组调查、竞品图片分析、视觉评分和设计 brief。

若用户选择图片设计，必须加载并使用 `amazon-image-design`。不要在本文案 skill 中继续执行图片设计细节，两个 skill 分开。

## COSMO / Alexa for Shopping Quality Checklist

最终交稿前检查：

- [ ] Title 是否 ≤75 characters including spaces（非 media 类目默认执行 2026 新规）。
- [ ] Item Highlights 是否 ≤125 characters，并与 Title 互补承接材料、用途、比较信息。
- [ ] 是否覆盖核心关键词 + 长尾关键词 + 场景语义词。
- [ ] 是否每个卖点都对应一个明确用户意图。
- [ ] 是否用“场景 + 问题 + 产品属性 + 收益”写清楚，而不是只列参数。
- [ ] Alexa for Shopping 是否能从文案中提取：适合谁、用在哪、解决什么、怎么用、规格是什么、材质是什么、如何安装/清洁/维护。
- [ ] COSMO 是否能识别产品与相关使用场景、互补需求、问题解决路径的关系。
- [ ] 是否避免绝对化和无法证明的宣称。
- [ ] 是否没有竞品品牌词、促销词、侵权词。
- [ ] 是否标注了缺失参数和待人工审核项。
- [ ] 上传版是否去掉 Markdown `**`。

## Compliance Guardrails

禁止杜撰：

- 尺寸、重量、容量、材质、数量、认证、电压、兼容性、质保、测试结果。

慎用或不用：

- best, cheap, free, sale
- 100%, guaranteed
- rust proof, predator proof, waterproof forever, indestructible
- medical/health cure claims
- made in USA，除非用户提供充分依据

推荐安全表达：

- helps block
- helps protect
- helps resist rust
- designed for outdoor use
- suitable for
- built for
- intended for

敏感品类：健康、安全、儿童、婴幼儿、补剂、医疗、化妆品、食品、电子认证等，必须标注“需人工合规审核”。

## Default Output Structure

When working on office/school supplies such as plastic folders with pockets, consult `references/office-supplies-folders.md` for reusable buyer-intent mapping, safe claim language, competitor pattern, and bullet ordering. When the task is competitor ASIN research for plastic folders by pack count / prongs / daily price, also consult `references/office-supplies-folder-competitor-research.md` for filtering rules, price verification, and concise table output.

When working on desktop file organizers, vertical file organizers, mesh mail holders, paper tray organizers, multi-component desk organizers, printer stands or monitor risers with storage, desk accessory sets, or office supplies sets for the US market—especially when the user asks only for title optimization or Item Highlights—consult `references/desktop-file-organizers-and-office-supplies.md` for concise title patterns, keyword priority, printer-stand and mesh-organizer examples, live-ASIN attribute discipline, and Item Highlights templates.

When working on mesh zipper pouches, A4/Letter document bags, classroom zipper bags, board-game bags, or puzzle-storage pouches for the US market, consult `references/mesh-zipper-pouches.md` for paper-size wording, 75-character title patterns, Item Highlights compression, buyer intents, and competitor-claim discipline.

When working on wall file organizers, hanging wall files, wall-mounted file holders, mail sorters, or magnetic file holders for refrigerators/file cabinets/whiteboards in the US market, consult `references/wall-file-organizers.md` for buyer-intent mapping, competitor-ASIN intake, 75-character title patterns, magnetic-surface limitations, dimension normalization, safe mounting/load claims, bullet order, and backend keyword candidates.

When working on kids' party favors / toy bulk packs such as mini squishy toys, soft rubber squeeze toys, classroom prizes, or goodie bag fillers, consult `references/kids-party-favors-squishy-toys.md` for naming conventions, buyer-intent mapping, compliant CPC/age wording, bullet ordering, and trademark-safe backend search terms.

When working on polycarbonate greenhouse panels / sheets, twin-wall greenhouse replacement panels, clear roof panels, or outdoor DIY roofing panels, consult `references/polycarbonate-greenhouse-panels.md` for buyer-intent mapping, 75-character title patterns, Item Highlights, bullet ordering, and safe weather/UV claims.

When working on greenhouse panels / polycarbonate sheets / greenhouse replacement panels, consult `references/greenhouse-polycarbonate-panels.md` for US buyer-intent mapping, title patterns, keyword layout, safe UV/weather/impact wording, and bullet ordering.

When working on manual floor scrub brushes, shower scrubbers with long handles, V-shaped corner/grout brushes, or floor brushes with silicone squeegees for the US market, consult `references/floor-scrub-brushes.md` for category positioning, buyer intent, VOC risks, safe surface claims, keyword priorities, bullet order, QA gates, and image-planning carryover.

When working on manual long-handle floor scrub brushes, shower scrubbers, deck brushes, grout/corner brushes, or 3-in-1 scrub brushes with an integrated squeegee for the US market, consult `references/long-handle-floor-scrub-brushes.md` for product classification, buyer intent, review-led differentiation, safe surface claims, QC priorities, and Rufus questions. Do not default to `push broom` or `mop` terminology when the product's primary job is scrubbing.

当进入最终交稿，默认使用下面结构：

```markdown
# 一、COSMO / Alexa for Shopping 文案重构逻辑
| 用户搜索意图 | 对应文案承接 |

# 二、关键词与语义词库
| 类型 | 词 | 数据/来源 | 布局建议 |

# 三、Title 标题（≤75 characters including spaces）
-English-:
...
-字符数-：...
-翻译-：
...

# 四、Item Highlights（≤125 characters, searchable）
-English-:
...
-字符数-：...
-翻译-：
...

# 五、Bullet Points 五行
## Bullet Point 1
-English-:
...
-翻译-：
...

# 六、Product Description 商品描述
-English-:
...
-翻译-：
...

# 七、Search Terms 后台搜索词
...

# 八、Alexa for Shopping 问答覆盖建议
...

# 九、COSMO / Alexa for Shopping 改进点
| 模块 | 旧版问题 | 新版调整 |

# 十、合规注意
...
```

## Hardware Cloth Example Pattern

如果产品是美国站 Hardware Cloth，可参考但不要机械套用：

推荐卖点顺序：

1. 19 Gauge Heavy-Duty Strength：解决买家担心网太薄、变形、不耐用。
2. 1/2 Inch Mesh Small-Pest Barrier：解决 rabbits / gophers / voles / small pests。
3. Galvanized Welded Outdoor Use：解决户外生锈、焊点稳定、雨水土壤环境。
4. 16 in x 50 ft Cut-to-Fit Project Roll：解释尺寸适合 coop panels、raised beds、tree guards、vents、rabbit hutches。
5. DIY Installation & Safety：wire cutters、staples、U-nails、zip ties、gloves、eye protection。

避免：

- 把 Multi-use 放第一卖点。
- 把尺寸放标题第一位而不是核心类目词。
- 使用 `rust proof` / `predator proof` 等绝对化表达。
- 使用 `Animal Cage Screen` 这类不地道表达，优先用 rabbit hutch / small animal enclosure / poultry run。

## Common Pitfalls

1. **直接写稿，跳过调研和审批。** 用户偏好阶段确认，除非明确要求直接输出。
2. **只埋关键词，不埋意图。** COSMO/购物助手审计重视上下文、场景和自然语言问题，但不存在公开的固定埋词公式。
3. **英译德/法关键词。** 多语站点必须用对应站点母语关键词数据。
4. **把 Markdown 加粗带进上传版。** 审核版可加粗，上传版必须删除 `**`。
5. **把竞品品牌放后台词。** 违规且有侵权风险。
6. **夸大功效。** 绝对化、防护类、健康类、安全类宣称必须谨慎。
7. **杜撰参数。** 没有数据就写“待补”，不要编。
8. **五点全是功能清单。** 每条必须有买家意图和场景收益。
9. **尺寸/适配类产品仍把规格埋在后面。** 板材、替换件、卷材等应把尺寸和数量前置；US 站优先换成 inch/ft。
10. **五点标题太长。** 用户要扫读时，标题短、正文长更好：标题抓意图，正文承接 COSMO/Rufus 语义、场景和情感价值。
11. **用户只要最终标题和五点时仍输出完整流程。** 若用户明确要求“只需要输出标题和五点”，最终回复只给 Title 与 Bullet Points；但在 2026 新规下可附加 Item Highlights，除非用户明确不要。
12. **用户要求“文字版”时仍使用代码块。** 当用户说“输出文字版即可”“不要代码框”“直接文字版”时，最终稿不要用 fenced code blocks；用普通文本标签（Title: / Item Highlights: / Bullet 1:）便于复制。
13. **沿用旧式 100–200 字符标题。** 2026-07-27 后非 media 类目标题默认 ≤75 characters；长标题信息要拆到 Item Highlights、五点、描述和后台词。
14. **把 Item Highlights 当后台词堆砌。** 它可搜索且前台可见，要写成买家能读懂的短说明，不能只是关键词串。

## Verification Checklist

- [ ] 已识别用户是要“文案创作”而不是单纯翻译或线上写操作。
- [ ] 已收集产品名和目标市场；缺失规格已标注。
- [ ] 已完成市场/受众/意图分析并获得用户认可，或用户明确要求跳过。
- [ ] 已完成产品参数解读并获得用户认可，或用户明确要求跳过。
- [ ] 已完成竞品分析，或确认用户不提供竞品。
- [ ] 已提炼并排序 5 个卖点。
- [ ] 已建立关键词 + 词根 + COSMO 语义词 + Rufus Q&A 词库。
- [ ] 最终 Title/Item Highlights/Bullets/Description/Search Terms/Q&A 已按目标站点语言输出。
- [ ] 中文翻译已提供。
- [ ] 合规风险与待补参数已明确标注。
- [ ] 如用户要求可上传版，已删除 Markdown `**`。
- [ ] 文案经用户确认后，已询问是否需要进入图片设计。
- [ ] 如进入图片设计，已按主图+7张辅图规划，并检查平台规则、卖点突出、尺寸像素、色彩、背景、排版、细节和图片文案。
