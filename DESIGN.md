# Amazon Copy Optimizer Design Contract

## 1. Direction

The product is a single-purpose conversational editorial workbench: send one existing Amazon
listing block with 1-10 copy points as a chat message, answer only targeted seller questions, and
receive one paste-ready result in the same conversation. The established visual direction is the
dark Lithos implementation in `amazon_copy/ui/app.py`: a near-black canvas, glass-like bordered
surfaces, orange actions, compact editorial hierarchy, and a clear conversation timeline.

The main canvas owns the seller-agent dialogue only. A persistent diagnostic sidebar owns every
workflow layer: route, source review, evidence, specialized rules, postflight review, and compatible
audit layers. Diagnostic detail never interrupts the conversation or appears between a question and
its answer.

The visible workbench runs an **evidence-first automatic workflow**. A single submit invokes the
typed orchestration service, which researches available MCP sources, resolves safe defaults, runs
source review, asks only targeted clarification questions when needed, and returns a postflight-safe
copy. The Studio graph remains a separate programmatic surface and does not generate the Streamlit
result.

## 2. Persona and decision path

The primary persona is a marketplace operator who already has listing copy and wants a faster,
clearer version without configuring an agent system. The complete decision path is:

```text
Seller message -> automatic research + source review -> agent clarification (when required)
               -> seller answer -> optimize -> postflight -> agent copy response
```

No market, locale, keywords, ASIN, seller, provider, Mock, HITL, or task-mode choice interrupts this
path. US and inferred Product Type remain invisible unless the service explicitly asks for them.
DeepSeek configuration remains server-side.

## 3. Tokens

The native theme in `.streamlit/config.toml` and the controlled `_THEME_CSS` style block in
`amazon_copy/ui/app.py` remain the token sources of truth:

| Role | Token |
| --- | --- |
| canvas | `#000000` |
| surface | `#141414` |
| raised surface | `#1A1A1A` |
| text | `#FFFFFF` |
| action orange | `#E8702A` |
| border | `#2A2A2A` / controlled white-alpha borders |
| typography scale | `--lithos-font-*` and `--lithos-line-*` |
| spacing and gaps | `--lithos-space-*` and `--lithos-gap-*` |
| corner radii | `--lithos-radius-*` |
| semantic states | `--lithos-*-strong`, `--lithos-*-subtle`, and `--lithos-*-border` |

Product Python modules keep colors in the shared theme tokens. Every Lithos chrome color, type
size, spacing value, gap, and radius is declared once under `:root` as a `--lithos-*` token; CSS
selectors consume those variables. A controlled custom CSS style block is permitted for the Lithos
chrome, and small semantic HTML wrappers are used for the eyebrow, title, subtitle, and section
labels. User/provider content must remain in safe native Streamlit text/widget APIs; do not
interpolate untrusted values into HTML.

## 4. Typography and spacing

- Display and body: Inter 300/400/500/600/700 with CJK-safe fallbacks (`Microsoft YaHei`,
  `PingFang SC`, `Noto Sans SC`, `Segoe UI`, sans-serif).
- Native Streamlit type sizes and vertical rhythm remain authoritative; custom chrome uses the
  `--lithos-font-*`, `--lithos-line-*`, and `--lithos-space-*` scale.
- A centered readable canvas replaces the former wide dashboard.
- Inputs stack in source order so the same sequence works at 375 px and desktop widths.

## 5. Native primitives and states

- Intro: caption, title, and one factual sentence describing the single workflow.
- Conversation start: one assistant welcome message and one bottom-pinned `st.chat_input`. The first
  seller message is the complete Listing; no separate source form or duplicate input box appears.
- Conversation history: render the submitted Listing as a user message and every system outcome as
  an assistant message. A new Listing starts a new source-bound run; the sidebar provides an explicit
  `新建对话` action.
- Clarification turn: when the service returns `needs_clarification`, render each exact question in
  the assistant message with native selection/text controls and the explicit
  `无法提供，删除该宣称` action. Answers resume with both source-bound caches; no MCP refetch occurs.
- Source boundary: parse title plus 1–10 points and a typed formatting template. Preserve recognizable
  title label and placement, section label, bullet marker family, ordering/count, blank-line grouping,
  and terminal punctuation as best effort. Preserve the source bullet count unless verified facts
  support the category target; never pad with invented or generic facts. Source text is untrusted
  content only.
- Diagnostic sidebar: route/status summary first, then source review, evidence, specialized-rule
  provenance, postflight review, and compatible audit layers. Each layer is a native expander; the
  currently blocking or clarifying layer opens by default. It contains field-level PASS/WARN/BLOCK,
  resolved facts, keyword coverage, ten independent scores, safe research basis, and rule gaps.
- Run result: the discriminated automatic result is rendered natively as completed,
  needs_clarification, or failed. Failed results expose sanitized errors and a retry only.
- Result: only a postflight result without BLOCK reaches an assistant response containing the
  editable copy surface. It contains Title, Item Highlights, the source bullet count/layout, and
  Backend Search Terms. Review and evidence detail remains in the sidebar.

### 5.1 Evidence and rule precedence

Conflicts resolve in this order: Amazon Product Type rules, category template/backend validators,
legal and safety requirements, packaging/manual/test/BOM/user-confirmed facts, Amazon first-party
keyword data, third-party/public data, competitor language, then writing hypotheses. Equal-priority
conflicts BLOCK generation. SellerSprite and Sorftime are optional priority-6, third-party-only MCP
sources: they may provide public market or keyword context, but cannot verify private product,
performance, or safety facts. Category constraints and evidence are resolved server-side; they are
not manual controls in the one-box UI.

Focus, hover, disabled, error, and success states remain Streamlit-native.

### 5.2 Specialized rule provenance primitive

The result and clarification surfaces include one native `专业规则配置` expander when a
source-bound `listing-optimize` profile route exists. It exposes only the allowlisted profile
filename, a short SHA-256 content-hash prefix, cache reuse state, and machine-readable rule-gap
codes. Raw rule Markdown, provider URLs, credentials, transport errors, and environment names
never render. A complete route is labelled `已加载`; a missing or partial route is labelled
`降级为通用门槛` and explicitly says that generic gates remain active without treating the gap as
verification. Internal guidance can shape copy instructions but cannot authorize a new fact.

When marketplace or Product Type routing is unresolved, the clarification form adds stable,
indexed native controls for `Marketplace` and `Product Type` alongside the existing confirm/remove
decision. Resume carries the source-bound research and specialized-rule cache; changing the source
fingerprint clears both caches and all dynamic clarification widgets.

### 5.3 Independent review state primitive

Each source and postflight review renders three separate native text states: `格式状态`, `事实状态`,
and `发布处置`. The existing aggregate PASS/WARN/BLOCK alert remains a summary only. Release
disposition values are `release`, `clarify`, or `block`; a postflight `block` keeps the copy area
absent even when format or fact details are shown.

## 6. Responsive behavior

- Desktop uses a readable conversation column with Streamlit's native sidebar as the diagnostic rail.
- At 375 px and 768 px the native sidebar collapses into Streamlit's drawer; the conversation,
  clarification controls, chat input, and result editor remain one vertical flow without overflow.
- At 1280 px the sidebar may remain open while the conversation keeps a readable line length.
- No tabs, fixed content widths, absolute positioning, viewport locks, or custom overflow behavior.

## 7. Accessibility and security

- The chat input has a descriptive placeholder that identifies the accepted whole-Listing message.
- The primary action has a text label and Material icon; no emoji iconography.
- Status and errors use both text and native semantic state, never color alone.
- Provider output renders through safe native Streamlit text APIs; only controlled static chrome uses
  semantic HTML alongside the theme style block.
- API keys, base URLs, model selectors, raw provider errors, and environment names are never sent to
  the browser, session state, downloads, or screenshots.

## 8. Pipeline architecture

The production Streamlit path is:

```text
source fingerprint -> parse -> safe research/cache -> resolve rules/evidence
      -> deterministic source review -> targeted clarification/resume
      -> one-role LLM edit -> deterministic postflight -> editable copy surface
```

The automatic result is a discriminated union of `completed`, `needs_clarification`, and `failed`:
the first exposes one postflight-safe copy result, the second exposes dynamic targeted questions,
and the third exposes only a sanitized retry. The postflight applies the same hard limits and
fact/risk gates as source review. Scores are not averaged and there is no overall score; a factual or
compliance BLOCK cannot be offset by strong language or SEO scores. MCP
snapshots and research gaps remain source-bound evidence, while market claims affect generation
only when normalized into allowable evidence. Specialized profile snapshots remain internal guidance
and never authorize facts. Any source mutation clears the result, clarification, research cache, and
specialized-rule cache state before rendering.

The Studio API and legacy CLI are separate programmatic surfaces; neither describes or populates the
visible one-box Streamlit result.

The **studio graph** (`run_studio_pipeline`, `amazon_copy.orchestrator.studio_graph`) is an
async 6-stage directed graph:

| Stage | What it does | Budget |
|-------|-------------|--------|
| Research | 5 MCP fixture lanes (no live Amazon) | `mcp_calls += 5` |
| Writers | 3 parallel LLM lanes → 3 candidates, each with 3 titles + 5 bullets | `llm_calls += 3` |
| Critique & revise | Ring-topology cross-review + revision | `llm_calls += 6` |
| Hard gates | Deterministic eligibility checks | — |
| Judges | Dual LLM judges rank eligible candidates | `llm_calls += 2` |
| Integrate | First-eligible selection | — |

**Budget caps** (see `BudgetLimits` in `amazon_copy.orchestrator.budgets`):
- Max 12 LLM calls per run
- Max 20 MCP calls per run
- Max 120 s wall-clock deadline

The pipeline defaults to **mock mode** (`Settings(MOCK=True)`) — fixture data from
`amazon_copy/mcp/fixtures/*.json` served by `build_fixture_provider`. No live Amazon,
no API key required.

The **legacy CLI** (`amz-copy run|write|optimize|seo|analyze`) uses the older `run_pipeline`
in `asyncio_pipeline.py` and remains fully supported.

## 9. Accepted debt and handoff

- Remote font URLs can fall back to installed fonts when offline.
- The synchronous provider call does not expose token streaming; `st.status` truthfully shows one
  bounded optimization operation.
- The old CLI and multi-stage pipeline remain supported but are not represented in this simplified
  visible workflow. The optimizer keeps its one-call path with one repair retry.
