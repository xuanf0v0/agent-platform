# Migration: Simple Optimizer → Studio Graph

## Overview

The v1 `run_pipeline` (`asyncio_pipeline.py`) was a linear step-by-step pipeline. The v2
studio graph (`run_studio_pipeline` / `StudioService`) is a 6-stage directed graph with
parallel writer lanes, ring-topology critique, dual judges, and typed budget enforcement.

Both programmatic pipelines coexist. The legacy CLI (`amz-copy`) still uses v1, while
`StudioService` exposes v2.

The Streamlit UI is the **product path**: automatic optimization with a thin control plane
(diagnose → approve → optimize). Studio and CLI are advanced/legacy surfaces.

## Automatic control plane: diagnose → approve → optimize

`run_automatic_optimization` (`amazon_copy.automatic_pipeline` / `simple_optimizer`) defaults to
Stage 1 analysis-first:

| Mode | Context | Terminal status | Copy exposed? |
|------|---------|-----------------|---------------|
| Stage 1 diagnose (default) | `mode="diagnose"`, `skip_approval=False` | `awaiting_approval` | No |
| Stage 2 optimize | `mode="optimize"` + valid `approval_token` | `completed` / `needs_clarification` / `failed` | Only if completed + postflight release |
| One-shot (legacy UX) | `skip_approval=True` | same as Stage 2 without token | Same |
| Stale token / edited source | `mode="optimize"` + wrong token | `failed` (`stale_approval`) | No |

Token material is deterministic: `sha256(source_fingerprint|finding_codes|disposition|salt)`.
It does **not** depend on LLM diagnosis digests. Stage 2 should pass Stage 1
`research_cache` / `specialized_rule_cache` / `rule_context` so MCP is not refetched.

Optional `ProductIdentity.asin` is display-only (10 alphanumeric chars, uppercased). Absence is
valid. Funnel hypotheses are copy-side assumptions (`confidence` ∈ {low, medium}) with a mandatory
non-root-cause disclaimer; no 赛狐 / CTR-CVR wiring in this layer.

Programmatic callers that previously assumed one-shot completion must set `skip_approval=True`
(or run Stage 2 with a token). Tests should do the same.

Canonical workflow states (`AWAITING_APPROVAL` in `canonical_workflow_states`) remain a separate
full state machine; Automatic uses a **lightweight semantic alignment** (token + fingerprint),
not the full `workflow_id` / revision machinery.

## Feature comparison

| Feature | Simple Optimizer (v1) | Studio Graph (v2) |
|---------|----------------------|-------------------|
| **Entry point** | `run_pipeline()` | `run_studio_pipeline()` / `StudioService.optimize_listing()` |
| **Output type** | `FinalPackage` | `StudioState` (with `CandidateArtifact` winner) |
| **Pipeline stages** | Research → Selling points → Title → BP write → SEO → Optimize → SEO2 → Scorecard | Research → 3 parallel writers → Critique & revise → Hard gates → Dual judges → Integrate |
| **Title output** | 1 winner + 5 candidates | 3 candidate titles per writer lane |
| **Bullet output** | 5 `BulletPoint` objects | 5 strings per `CandidateArtifact` |
| **Research** | LLM-synthesized from ProductInput | 5 MCP fixture lanes (no live Amazon) |
| **Mock data** | Mock LLM responses | Deterministic JSON fixture files + `FixtureMcpServer` |
| **Budget enforcement** | `CallCounter` (LLM calls only) | `BudgetLedger` (LLM + MCP caps + deadline) |
| **Default budget** | 12 LLM | 12 LLM + 20 MCP + 120 s |
| **Critique** | None | Ring-topology: each candidate reviewed by 2 peers, then revised |
| **Hard gates** | None (validation via pydantic contexts) | Deterministic eligibility checks before judging |
| **Judging** | None (single scorecard) | Dual LLM judges, ranked by combined score |
| **Integration** | Direct `ListingDraft` from first pass | First-eligible winner from ranked candidates |
| **SEO audit** | 2-pass: `seo` + `seo2` | Not in graph (post-processing via `package_from_studio_state`) |
| **Export** | `export_package()` → JSON/MD/report | `package_from_studio_state()` maps to `FinalPackage` for legacy export |
| **CLI** | `amz-copy run\|write\|optimize\|seo\|analyze` | Same CLI (still uses v1 internally) |
| **Streamlit** | Not part of the legacy CLI migration | Product path: two-stage Automatic (`diagnose` → approve → `optimize`) via `run_automatic_optimization`; optional ASIN display; funnel hypotheses; clarification + postflight gates unchanged |

## Schema notes

| Schema | v1 location | v2 location | Key differences |
|--------|-------------|-------------|-----------------|
| Product input | `ProductInput` | `StudioRequest` | v2 uses a frozen `BaseModel` with `request_hash`, typed `SellerAssertion`, `EvidenceGap` |
| Listing draft | `ListingDraft` (title + 5 BP + candidates) | `CandidateArtifact` (3 titles + 5 bullets, per lane) | v2 has 3 parallel candidates, not 1 |
| Final package | `FinalPackage` | `StudioState` | v2 state is a frozen dataclass with typed outcomes |
| Research bundle | `ResearchPack` | `ResearchBundle` (per-lane dict in `state.research`) | v2 uses MCP protocol with `ResearchClaim` / `ResearchResult` |
| Budget | `Settings.max_llm_calls` | `BudgetLimits` + `BudgetLedger` | v2 adds `max_mcp_calls` and `run_deadline_seconds`, both independently enforced |

## Upgrading custom code

If you were calling `run_pipeline()` directly, the migration path is:

1. Replace `from amazon_copy.orchestrator import run_pipeline` with
   `from amazon_copy.orchestrator.studio_graph import run_studio_pipeline`.
2. Wrap your product text in a plain string (the graph parses it into a `StudioRequest`).
3. Check `state.outcome` for the result (not `FinalPackage.stage`).
4. Read the winner via `state.winner.titles` (3 strings) and `state.winner.bullets` (5 strings).
5. Optionally pass a `BudgetLedger` for budget enforcement.
6. Use `package_from_studio_state()` if you need a `FinalPackage` for legacy export.

For the Streamlit UI product path: paste one listing → **自动分析** (Stage 1) → review diagnosis
and funnel hypotheses → **生成上传稿** (Stage 2). Check **跳过诊断，直接优化** for the previous
one-shot behavior. Callers of `run_automatic_optimization` that expected immediate `completed`
must pass `skip_approval=True` or complete the approve step with a valid token.

## Specialized-rule UI observability

The automatic one-box result now reports the exact allowlisted `listing-optimize` profiles selected
for the resolved marketplace and Product Type, short content-hash prefixes, source-bound cache reuse,
and machine-readable rule gaps. Only native text rows are rendered; profile Markdown, URLs,
credentials, provider error details, and environment names stay server-side. Profile load failure is
shown as a degraded generic-gate fallback rather than a verification claim.

Source and postflight review cards expose three independent states: `格式状态`, `事实状态`, and
`发布处置`. A postflight `block` keeps the optimized copy hidden. When routing needs both marketplace
and Product Type, the clarification form renders stable keyed controls for both in one turn. Resume
passes the source-bound research and specialized-rule caches back to the automatic service, so no MCP
refetch occurs; changing the listing clears that state.
