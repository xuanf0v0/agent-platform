import { FormEvent, useMemo, useState } from "react";
import { optimizeListing } from "./api";
import type { OptimizeContext, WorkflowResult } from "./types";

const stages = ["解析 Listing", "市场研究", "规则与事实核查", "Stage 1 诊断", "生成与发布门禁"];
const funnelLabels: Record<string, string> = {
  exposure: "曝光",
  ctr: "点击率 CTR",
  cvr: "转化率 CVR",
  cart_to_purchase: "加购→购买",
};

function resumableContext(result: WorkflowResult, overrides: OptimizeContext): OptimizeContext {
  const evidence = (result.evidence_bundle ?? {}) as Record<string, unknown>;
  return {
    rule_context: result.rule_context ?? undefined,
    user_claims: evidence.user_claims as OptimizeContext["user_claims"],
    suppressed_claim_terms: evidence.suppressed_claim_terms as OptimizeContext["suppressed_claim_terms"],
    allowed_keywords: evidence.allowed_keywords as OptimizeContext["allowed_keywords"],
    cached_research: result.research_cache ?? undefined,
    cached_specialized_rules: result.specialized_rule_cache ?? undefined,
    clarification_questions: result.questions,
    ...overrides,
  };
}

function JsonPanel({ title, value, open = false }: { title: string; value: unknown; open?: boolean }) {
  if (!value) return null;
  return (
    <details className="report" open={open}>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Status({ status }: { status: string }) {
  const names: Record<string, string> = {
    awaiting_approval: "等待确认",
    needs_clarification: "需要澄清",
    completed: "已完成",
    failed: "未完成",
  };
  return <span className={`status ${status}`}>{names[status] ?? status}</span>;
}

function SidePanel({ result, currentStage }: { result: WorkflowResult | null; currentStage: number }) {
  const hypotheses = result?.funnel_hypotheses ?? [];
  return (
    <aside className="side-panel">
      <section>
        <p className="section-kicker">WORKFLOW</p>
        <h2>运行状态</h2>
        <div className="progress-track"><i style={{ width: `${(currentStage / stages.length) * 100}%` }} /></div>
        {stages.map((stage, index) => {
          const done = index + 1 < currentStage;
          const active = index + 1 === currentStage;
          return <p className={`stage ${done ? "done" : active ? "active" : ""}`} key={stage}><b>{done ? "✓" : active ? "●" : "○"}</b>{stage}</p>;
        })}
      </section>
      {result && (
        <section className="side-section">
          <Status status={result.status} />
          {result.identity && <p className="identity">{[result.identity.asin, result.identity.marketplace, result.identity.product_type].filter(Boolean).join(" · ")}</p>}
        </section>
      )}
      {hypotheses.length > 0 && (
        <section className="side-section">
          <h3>漏斗假设</h3>
          {hypotheses.map((item) => <div className="hypothesis" key={`${item.stage}-${item.note_zh}`}><b>{funnelLabels[item.stage] ?? item.stage}</b><small>{item.confidence}</small><p>{item.note_zh}</p></div>)}
        </section>
      )}
    </aside>
  );
}

export default function App() {
  const [source, setSource] = useState("");
  const [asin, setAsin] = useState("");
  const [skipApproval, setSkipApproval] = useState(false);
  const [reply, setReply] = useState("");
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [approvalToken, setApprovalToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const stage = useMemo(() => {
    if (result?.status === "completed") return 5;
    if (result?.status === "awaiting_approval") return 4;
    if (result?.status === "needs_clarification") return 3;
    if (busy) return 2;
    return result ? 1 : 0;
  }, [busy, result]);
  const buttonLabel = busy
    ? "处理中…"
    : result?.status === "awaiting_approval"
      ? "确认并生成上传稿"
      : result?.status === "needs_clarification"
        ? "提交确认"
        : "开始诊断";

  async function run(context: OptimizeContext) {
    setBusy(true);
    setError("");
    try {
      const next = await optimizeListing(source, context);
      setResult(next);
      if (next.approval_token) setApprovalToken(next.approval_token);
      setReply("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (result?.status === "awaiting_approval") {
      void run(resumableContext(result, { mode: "optimize", approval_token: approvalToken || result.approval_token }));
      return;
    }
    if (result?.status === "needs_clarification") {
      const resumeOptimization = Boolean(result.postflight_review) || Boolean(approvalToken);
      void run(resumableContext(result, {
        mode: resumeOptimization ? "optimize" : "diagnose",
        skip_approval: !approvalToken && skipApproval,
        approval_token: resumeOptimization ? approvalToken || undefined : undefined,
        clarification_reply: reply,
      }));
      return;
    }
    const normalizedAsin = asin.trim().toUpperCase();
    void run({
      mode: skipApproval ? "optimize" : "diagnose",
      skip_approval: skipApproval,
      identity: /^[A-Z0-9]{10}$/.test(normalizedAsin) ? { asin: normalizedAsin } : undefined,
    });
  }

  function reset() {
    setSource("");
    setAsin("");
    setReply("");
    setResult(null);
    setApprovalToken("");
    setError("");
  }

  function retry() {
    if (result) void run(resumableContext(result, { mode: "diagnose", skip_approval: skipApproval }));
  }

  async function copyOutput() {
    if (result?.rendered_text) await navigator.clipboard.writeText(result.rendered_text);
  }

  const invalidAsin = Boolean(asin.trim() && !/^[A-Za-z0-9]{10}$/.test(asin.trim()));

  return (
    <main>
      <header>
        <div><p className="eyebrow">AMAZON LISTING OPTIMIZATION</p><h1>文案诊断与安全改写</h1><p className="subtitle">粘贴完整 Listing，先审阅诊断，再确认生成可复制上传稿</p></div>
        <button className="button ghost" onClick={reset}>新建对话</button>
      </header>
      <div className="workspace">
        <section className="main-panel">
          <form onSubmit={submit}>
            <div className="input-header"><div><p className="section-kicker">SOURCE LISTING</p><h2>原始 Listing</h2></div><span>{source.length.toLocaleString()} 字符</span></div>
            <textarea className="source-input" value={source} onChange={(event) => { setSource(event.target.value); if (result) setResult(null); }} placeholder="粘贴标题、Item Highlights 和五点描述…" required disabled={busy} />
            <div className="form-options">
              <label>ASIN（可选）<input value={asin} onChange={(event) => setAsin(event.target.value)} maxLength={10} placeholder="B0XXXXXXXX" disabled={busy} /></label>
              <label className="check"><input type="checkbox" checked={skipApproval} onChange={(event) => setSkipApproval(event.target.checked)} disabled={busy} />跳过诊断，直接优化</label>
            </div>
            {invalidAsin && <p className="hint">ASIN 须为 10 位字母或数字；无效输入会被忽略</p>}
            {result?.status === "needs_clarification" && (
              <section className="clarify"><p className="section-kicker">FACT CONFIRMATION</p><h2>需要确认的事实</h2>{result.questions?.map((question, index) => <div className="question" key={question.code}><b>{index + 1}. {question.question_zh}</b><small>所需依据：{question.evidence_needed || "请提供可验证来源"}</small></div>)}<textarea value={reply} onChange={(event) => setReply(event.target.value)} placeholder="逐项确认；无法确认可写“删除该宣称”" required /></section>
            )}
            {error && <p className="error">{error}</p>}
            <button className="button primary" disabled={busy || !source.trim()}>{buttonLabel}</button>
          </form>
          {result && (
            <section className="result-area">
              <div className="result-title"><div><p className="section-kicker">RESULT</p><h2>{result.status === "completed" ? "优化后 Listing" : result.status === "awaiting_approval" ? "诊断已完成" : result.status === "failed" ? "本次未完成" : "等待事实确认"}</h2></div><Status status={result.status} /></div>
              {result.status === "completed" && <><div className="copy-row"><p>已通过优化后发布门禁，可编辑并复制</p><button className="button ghost" type="button" onClick={() => void copyOutput()}>复制原始生成稿</button></div><textarea className="output" defaultValue={result.rendered_text ?? ""} /></>}
              {result.status === "awaiting_approval" && <><p>已完成源稿诊断。请查看右侧运行信息和下方报告，确认后生成上传稿</p>{result.diagnosis_report && <p className="metric">编辑评分平均：{String(result.diagnosis_report.average_score ?? "—")}/10</p>}</>}
              {result.status === "failed" && <><p className="error">{result.message}</p>{result.last_candidate_text && <><p>以下为未通过质量门禁的最后一轮稿件，不可直接发布</p><textarea className="output" defaultValue={result.last_candidate_text} /></>}{result.quality_failures && <ul>{result.quality_failures.map((failure) => <li key={failure}>{failure}</li>)}</ul>}<button type="button" className="button ghost" onClick={retry} disabled={busy}>重试</button></>}
            </section>
          )}
        </section>
        <SidePanel result={result} currentStage={stage} />
      </div>
      {result && <section className="reports"><p className="section-kicker">AUDIT & EVIDENCE</p><h2>审核与依据</h2><div className="report-grid"><JsonPanel title="源稿诊断报告" value={result.diagnosis_report} open={result.status === "awaiting_approval"} /><JsonPanel title="原始 Listing 审核" value={result.source_review} /><JsonPanel title="优化后审核 · 发布门禁" value={result.postflight_review} open={result.status === "completed"} /><JsonPanel title="规则上下文" value={result.rule_context} /><JsonPanel title="安全市场研究依据" value={result.research_cache} /><JsonPanel title="专业规则配置" value={result.specialized_rule_cache} /></div></section>}
    </main>
  );
}
