import { FormEvent, useMemo, useState } from "react";
import { advanceCopyWorkflow, optimizeListing } from "./api";
import type { CopyWorkflow, CopyWorkflowView, OptimizeContext, WorkflowResult } from "./types";

const workflowNames: Record<CopyWorkflow, string> = { write: "标题与五行撰写", optimize: "五行优化", seo: "SEO 分析", analyze: "文案分析" };
const fieldNames: Record<string, string> = { product_name: "产品名称", target_market: "目标市场", product_manual: "产品说明书 / 规格参数", competitor_copy_optional: "竞品标题与五行（没有可填“跳过”）", top20_rootwords: "TOP20 词根", top20_keywords: "TOP20 关键词", five_bullets: "五行文案" };
const approvalSteps = new Set(["market_research", "product_analysis", "competitor_analysis", "selling_points", "source_analysis", "seo_needs"]);

function SafeOptimizer() {
  const [source, setSource] = useState(""); const [result, setResult] = useState<WorkflowResult | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function run(context: OptimizeContext) { setBusy(true); setError(""); try { setResult(await optimizeListing(source, context)); } catch (reason) { setError(reason instanceof Error ? reason.message : "请求失败"); } finally { setBusy(false); } }
  function submit(event: FormEvent) { event.preventDefault(); if (result?.status === "awaiting_approval") void run({ mode: "optimize", approval_token: result.approval_token, rule_context: result.rule_context, cached_research: result.research_cache, cached_specialized_rules: result.specialized_rule_cache }); else void run({ mode: "diagnose" }); }
  return <section className="agent-panel"><h2>Listing 安全优化 Agent</h2><p className="muted">先诊断和确认，再生成可上传稿</p><form onSubmit={submit}><label>原始 Listing<textarea value={source} onChange={event => setSource(event.target.value)} required disabled={busy || Boolean(result)} /></label>{error && <p className="error">{error}</p>}<button className="primary" disabled={busy}>{busy ? "处理中…" : result?.status === "awaiting_approval" ? "确认并生成" : "开始诊断"}</button></form>{result && <div className="result"><span className={`status ${result.status}`}>{result.status}</span>{result.rendered_text && <textarea readOnly value={result.rendered_text} />}<details><summary>运行详情</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></div>}</section>;
}

function CopyStudio() {
  const [workflow, setWorkflow] = useState<CopyWorkflow>("write"); const [view, setView] = useState<CopyWorkflowView | null>(null);
  const [values, setValues] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const state = view?.state ?? { workflow, step: "basic_input", revision: 0 };
  const fields = view?.required_inputs ?? (workflow === "write" ? ["product_name", "target_market"] : workflow === "optimize" ? ["product_name", "target_market", "five_bullets", "top20_rootwords", "top20_keywords"] : workflow === "seo" ? ["target_market", "five_bullets", "top20_rootwords", "top20_keywords"] : ["five_bullets", "top20_rootwords", "top20_keywords"]);
  const needsApproval = approvalSteps.has(state.step); const progress = useMemo(() => view ? Math.round((view.route.indexOf(state.step) / (view.route.length - 1)) * 100) : 0, [view, state.step]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { setView(await advanceCopyWorkflow(state, values, needsApproval ? true : undefined)); setValues({}); } catch (reason) { setError(reason instanceof Error ? reason.message : "请求失败"); } finally { setBusy(false); } }
  function reset(next: CopyWorkflow) { setWorkflow(next); setView(null); setValues({}); setError(""); }
  return <section className="agent-panel"><h2>Listing 创作 Agent</h2><div className="tabs">{(Object.keys(workflowNames) as CopyWorkflow[]).map(item => <button className={workflow === item ? "active" : ""} onClick={() => reset(item)} key={item}>{workflowNames[item]}</button>)}</div><div className="progress"><i style={{ width: `${progress}%` }} /></div><p><b>当前步骤：</b>{state.step}</p>{view?.completed ? <div className="done"><h3>流程已完成</h3><p>所有必填信息与确认门禁均已完成，可进入对应执行服务生成结果</p></div> : <form onSubmit={submit}>{fields.map(field => <label key={field}>{fieldNames[field] ?? field}<textarea value={values[field] ?? ""} onChange={event => setValues(current => ({ ...current, [field]: event.target.value }))} required /></label>)}{fields.length === 0 && <p className="notice">此步骤将执行分析。请确认分析结果后继续</p>}{error && <p className="error">{error}</p>}<button className="primary" disabled={busy}>{busy ? "处理中…" : needsApproval ? "认可并进入下一步" : "提交并继续"}</button></form>}</section>;
}

export default function App() { const [active, setActive] = useState<"home" | "safe" | "studio">("home"); return <main><header><div><p className="eyebrow">AMAZON LISTING OPTIMIZATION</p><h1>Listing 优化 Agent</h1><p className="subtitle">诊断、分析与安全优化工作台</p></div>{active !== "home" && <button className="ghost" onClick={() => setActive("home")}>返回</button>}</header>{active === "home" ? <div className="agent-grid"><button className="agent-card" onClick={() => setActive("safe")}><small>OPTIMIZE</small><h2>Listing 安全优化</h2><p>诊断现有文案、人工确认、安全改写与发布门禁</p><b>进入 →</b></button><button className="agent-card" onClick={() => setActive("studio")}><small>ANALYZE</small><h2>文案分析工作室</h2><p>五行优化、SEO 与文案质量分析辅助流程</p><b>进入 →</b></button></div> : active === "safe" ? <SafeOptimizer /> : <CopyStudio />}</main>; }
