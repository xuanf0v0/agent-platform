# Amazon Copy Agent

A Streamlit listing workbench with a **product control plane** (diagnose → approve → generate)
on top of a **safe copy execution plane** (research → review → optimize → postflight).
Paste one existing listing (optional ASIN for display only), review Stage 1 diagnosis and
copy-side funnel hypotheses, then approve generation. Only postflight-safe copy is exposed
for copying. Clarification gates still pause when facts cannot be safely inferred.

The project exposes **three execution surfaces**:

| Pipeline | Entry point | Description |
|----------|-------------|-------------|
| **Automatic (product path)** | `streamlit run amazon_copy/ui/app.py` / `run_automatic_optimization` | Default two-stage: Stage 1 diagnose → `awaiting_approval` → seller clicks **生成上传稿** → Stage 2 safe rewrite + postflight. Optional ASIN identity display; optional **跳过诊断，直接优化** (`skip_approval=True`) restores one-shot optimize. |
| **Studio graph** (advanced) | `StudioService.optimize_listing()` / `run_studio_pipeline()` | 6-stage multi-agent graph: research → 3 parallel writers → critique & revise → hard gates → dual judges → integrate. Produces a `CandidateArtifact` with exactly 3 titles and 5 bullets. Not the default product path. |
| **Legacy CLI** (legacy) | `run_pipeline()` / `amz-copy run\|write\|optimize\|seo\|analyze` | Step-by-step research → write → optimize → SEO → scorecard. The five CLI commands still work unchanged. |

**Legacy CLI title modes:** `sop_seo` targets 100–200 characters; `strict_amazon` enforces 1–80.
All character checks use plain text after removing internal `**keyword**` audit markers.

## Install

Python 3.11 or newer is required.

```powershell
cd D:\demo\amazon_copy_agent
pip install -e ".[dev]"
```

## Automatic Streamlit workflow (product path)

Run the web app and paste the complete existing listing into the single `原始 Listing` box.
Optionally enter a 10-character **ASIN** for identity display only (never guessed; paste-only
still works). The server keeps provider and model configuration private, uses any configured MCP
services to collect safe research evidence, and applies deterministic source review before the
model edits anything.

### Two-stage control plane (default)

1. **Stage 1 — 自动分析** (`mode="diagnose"`): research cache → specialized rules → source review
   → diagnosis → optional clarification. On success the result is `awaiting_approval` (no copy
   surface). Side panel shows diagnosis, source review states, optional identity, and **漏斗假设**
   (copy-side only; confidence ≤ medium; always disclaimer — not measured CTR/CVR root cause).
2. **Stage 2 — 生成上传稿**: reuses Stage 1 caches + `approval_token` bound to source fingerprint
   and deterministic review codes. Runs optimize → polish → postflight. Editing the listing
   invalidates the token (`stale_approval`).
3. **跳过诊断，直接优化**: sets `skip_approval=True` for the previous one-shot optimize path.

Result union: `completed` | `awaiting_approval` | `needs_clarification` | `failed`.
Clarification answers resume from the source-bound research cache; they do not trigger a second
MCP fetch. Programmatic callers that want the old one-shot behavior should pass
`AutomaticOptimizationContext(skip_approval=True)` (or `mode="optimize"` with a valid token).

Completed API runs also emit a best-effort, read-only editorial shadow observation to
`.amazon_copy/observations/editorial-shadow.jsonl` when `EDITORIAL_SHADOW_ENABLED=true` (default).
It reuses existing diagnosis/postflight scores, adds no model or MCP calls, never changes the
publishable result, and stores only version/run metadata, hashes, scores, and stable issue codes.
Set the flag to `false` to disable observation entirely.

SellerSprite and Sorftime are optional priority-6, third-party-only MCP sources. They can contribute
public market or keyword context, but they cannot verify private product facts, test/BOM evidence,
or performance and safety claims. Such claims remain unresolved until supported by authoritative
or seller-provided evidence. Review dimensions stay independent and there is no overall score.

When an exact `listing-optimize` route is available, the result exposes the selected allowlisted
profile filenames, short SHA-256 content-hash prefixes, cache reuse, and any safe rule-gap codes in
the `专业规则配置` panel. Profile Markdown, provider URLs, credentials, transport error text, and
environment names are never rendered. A missing or partial route is explicitly shown as a degraded
generic-gate fallback and is never presented as product evidence. The source and postflight reports
keep `格式状态`, `事实状态`, and `发布处置` separate; a postflight `block` has no copy result.

If English source text leaves US/UK unresolved, the clarification form asks for `Marketplace` and
can ask for `Product Type` in the same turn. Both controls have stable indexed keys. Submitting the
answers resumes the source-bound research and specialized-rule cache without refetching MCP data;
editing the listing starts a fresh source fingerprint and clears both caches.

## Separate Studio pipeline

The **studio graph** (`run_studio_pipeline` in `amazon_copy.orchestrator.studio_graph`) is a 6-stage async graph that runs entirely offline in mock mode:

1. **Research** — MCP research lanes (fixture provider, no live Amazon)
2. **Writers** — 3 parallel LLM lanes (SEO, Differentiation, Clarity), each producing a candidate with **3 titles + 5 bullets**
3. **Critique & revise** — ring-topology cross-review and revision
4. **Hard gates** — deterministic eligibility checks (no I/O)
5. **Judges** — dual-judge ranking
6. **Integrate** — first-eligible selection

### StudioService

The `StudioService` facade (`amazon_copy.studio`) provides sync and async entry points:

```python
from amazon_copy.studio import StudioService

service = StudioService()
state = service.optimize_listing("USB-C Hub 7-in-1")
print(state.outcome, state.winner)
```

Constructed with no arguments it defaults to mock mode — no API key, no network.

### Budget defaults

Every studio run enforces hard caps via `BudgetLedger` (`amazon_copy.orchestrator.budgets`):

| Resource | Default cap |
|----------|-------------|
| LLM calls | 12 |
| MCP calls | 20 |
| Wall-clock deadline | 120 s |

These match the `Settings` defaults in `amazon_copy.config`. Exceeding any cap raises a typed rejection (`BudgetExhausted` / `DeadlineExceeded`).

### MOCK offline fixtures + fixture MCP

No live Amazon calls are made. Research data comes from **deterministic JSON fixture files** (`amazon_copy/mcp/fixtures/*.json`) served through a **fixture MCP server** (`amazon_copy.mcp.fixture_server.build_fixture_provider`).

- Five fixture roles: `shopper`, `policy`, `competitor`, `keyword`, `product`
- Modes: `fresh` (default), `stale`, `conflict`, `malformed`, `hang`
- The pipeline auto-creates a fixture provider when `settings.mock=True` and no provider is injected

### Canonical output shape

When the graph succeeds, the winner `CandidateArtifact` contains **exactly 3 title strings** and **exactly 5 bullet strings**:

```python
assert len(state.winner.titles) == 3   # canonical 3 titles
assert len(state.winner.bullets) == 5  # canonical 5 bullets
```

### No credentials in browser

The Streamlit UI (`streamlit run amazon_copy/ui/app.py`) never sends API keys, base URLs, model names, or environment variables to the browser. All provider configuration stays server-side in `.env`.

## Separate legacy CLI — still works

The original five CLI modes remain fully supported:

| Command | Description |
|---------|-------------|
| `amz-copy run --mock --product ...` | Full research → write → optimize → SEO → score path |
| `amz-copy write --mock --product ...` | Stop after first SEO check; `--full-checks` runs the rest |
| `amz-copy optimize -b "..." -b "..."` | Optimize exactly five existing bullet points |
| `amz-copy seo -b "..." -b "..."` | Deterministic SEO V/X tables |
| `amz-copy analyze -b "..." -b "..."` | Score across nine fixed dimensions |

Run offline in one command:

```powershell
amz-copy run --mock --product "USB C Hub" --market US --instruction "7-in-1 hub" --rootwords "usb,hub,adapter,hdmi,macbook,port,multiport,laptop,apple,usbc,card,mac,dongle,pd,charging,4k,sd,microsd,chrome,dell,ipad" --keywords "usb hub,usb c hub,usb-c hub,multiport adapter,hdmi hub,pd charging,4k hdmi,macbook hub,laptop hub,sd card reader" --output outputs/smoke
```

This writes:

- `listing.json`: the complete machine-readable `FinalPackage`
- `listing.md`: paste-ready plain title and five bullet points, plus Chinese reference text
- `listing_marked.md`: the same listing with internal keyword/rootword markers retained
- `report.md`: research, ranked selling points, SEO V/X tables, and scorecard

Existing files with these names are safely replaced.

## Use a real OpenAI-compatible API

Copy `.env.example` to `.env`, then configure at least:

```dotenv
OPENAI_API_KEY=your-key
OPENAI_API_BASE=https://api.deepseek.com
WRITER_MODEL=deepseek-v4-flash
REVIEW_MODEL=deepseek-v4-flash
VOTE_MODEL=deepseek-v4-flash
```

Run the same command without `--mock`. Credentials are read from the environment or local `.env`; never pass or commit keys in copy inputs.

## Commands and input rules

```powershell
amz-copy run --help       # full research → write → optimize → SEO → score path
amz-copy write --help     # stop after the first SEO check; --full-checks runs the rest
amz-copy optimize --help  # optimize exactly five repeated --bullet/-b values
amz-copy seo --help       # deterministic V/X tables for five --bullet values
amz-copy analyze --help   # score title + five --bullet values
```

`--rootwords` and `--keywords` accept either `,` or `，`. `run` and `write` accept an optional `--seller-name`; in `strict_amazon` mode that known identity is excluded from generated titles, while an omitted value is never inferred. US, UK, CA, AU and their common Chinese aliases default to English output; another market must specify `--locale`. Chinese translations are always emitted. `--hitl` adds only three confirmations to the write path: research, selling points, and listing draft. Automation remains the default.

## Streamlit one-box app

```powershell
streamlit run amazon_copy/ui/app.py
```

The visible UI is one vertical product flow: paste a whole listing (optional ASIN), press
`自动分析`, review Stage 1 diagnosis / funnel hypotheses / evidence, then press **生成上传稿**
for postflight-safe copy. Use **跳过诊断，直接优化** when you want one-shot generation.
Clarification still appears when facts cannot be safely inferred. Keep mock mode enabled for a
fully offline demonstration; real mode reads provider and model settings from the server-side
`.env` and never exposes credentials to the browser.

**Advanced / legacy:** Studio multi-candidate graph and `amz-copy` CLI remain available; they are
not the default product path.

## Scope and research limitations

Research is constrained to configured MCP sources and the pasted listing. SellerSprite and Sorftime
are priority-6, third-party-only sources: their public context cannot independently verify private product,
performance, or safety facts. The agent does **not** scrape Amazon or treat third-party text as product
evidence, so factual, legal, localization, and compliance statements still need authoritative support.

This v1 writes and audits Title + five Bullet Points. It does not publish to Seller Central, call SP-API, scrape live listings, generate required A+ content, provide category-specific policy guarantees, or replace final seller review. COSMO/A9 appear only as copy-intent guidance and SEO narrative context, not as a proprietary ranking scorer.
