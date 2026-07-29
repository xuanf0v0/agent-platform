import { FormEvent, useState } from "react";

import { sendTurn, uploadImages } from "./api";
import type { CreationSession, Deliverable } from "./types";

const stages = [
  "brief",
  "audience",
  "product",
  "competitor",
  "selling_points",
  "keywords",
  "final_copy",
  "image_handoff",
  "image_analysis",
  "image_plan",
];

const labels: Record<string, string> = {
  brief: "Brief 与事实台账",
  audience: "受众与市场",
  product: "产品解读",
  competitor: "竞品分析",
  selling_points: "五大卖点",
  keywords: "关键词意图",
  final_copy: "最终文案",
  image_handoff: "图片交接",
  image_analysis: "图片组分析",
  image_plan: "主图 + 7 辅图",
  completed: "完成",
};

function CopyField({ label, value, translation }: { label: string; value: string; translation?: string }) {
  if (!value) return null;
  return (
    <label className="copy-field">
      <span>{label}</span>
      <textarea readOnly value={value} />
      {translation && <small>{translation}</small>}
    </label>
  );
}

function DeliverablePanel({ deliverable }: { deliverable: Deliverable }) {
  return (
    <section className="deliverable panel-block">
      <div className="section-head">
        <div>
          <p className="kicker">UPLOAD-READY COPY</p>
          <h2>可复制成稿</h2>
        </div>
        <span className={`policy policy-${deliverable.policy_status.toLowerCase()}`}>
          {deliverable.policy_status}
        </span>
      </div>
      <div className="metrics-line">
        <span>Title {deliverable.title_chars}/75</span>
        <span>Highlights {deliverable.item_highlights_chars}/125</span>
        <span>Search Terms {deliverable.search_terms_bytes}/250 bytes</span>
      </div>
      <CopyField label="Title" value={deliverable.title} translation={deliverable.title_zh} />
      <CopyField
        label="Item Highlights"
        value={deliverable.item_highlights}
        translation={deliverable.item_highlights_zh}
      />
      {deliverable.bullets.map((bullet, index) => (
        <CopyField key={index} label={`Bullet ${index + 1}`} value={bullet.text} translation={bullet.text_zh} />
      ))}
      <CopyField label="Product Description" value={deliverable.product_description} translation={deliverable.product_description_zh} />
      <CopyField label="Backend Search Terms" value={deliverable.search_terms} />

      <div className="detail-grid">
        {deliverable.shopping_questions.length > 0 && (
          <article className="detail-card">
            <h3>Alexa Shopping 问题覆盖</h3>
            {deliverable.shopping_questions.map((item, index) => (
              <div className="qa" key={index}>
                <strong>{item.question}</strong>
                <p>{item.answer_basis}</p>
                {item.answer_zh && <small>{item.answer_zh}</small>}
              </div>
            ))}
          </article>
        )}
        {deliverable.a_plus_modules.length > 0 && (
          <article className="detail-card">
            <h3>A+ / EBC 架构</h3>
            {deliverable.a_plus_modules.map((item, index) => (
              <div key={index} className="list-row">
                <strong>{item.module}</strong>
                <span>{item.purpose}</span>
                <p>{item.content}</p>
              </div>
            ))}
          </article>
        )}
        {deliverable.category_recommendations.length > 0 && (
          <article className="detail-card">
            <h3>类目 / Browse Node 候选</h3>
            {deliverable.category_recommendations.map((item, index) => (
              <div key={index} className="list-row">
                <strong>{item.path}</strong>
                {item.node_id_path && <code>{item.node_id_path}</code>}
                <p>{item.basis} · {item.verification}</p>
              </div>
            ))}
          </article>
        )}
        {Object.keys(deliverable.keyword_intent_map).length > 0 && (
          <article className="detail-card">
            <h3>关键词与意图布局</h3>
            {Object.entries(deliverable.keyword_intent_map).map(([field, terms]) => (
              <div key={field} className="list-row"><strong>{field}</strong><p>{terms.join(" · ")}</p></div>
            ))}
          </article>
        )}
        {deliverable.claim_evidence_map.length > 0 && (
          <article className="detail-card">
            <h3>宣称与证据映射</h3>
            {deliverable.claim_evidence_map.map((item, index) => (
              <div key={index} className="list-row"><strong>{item.claim}</strong><p>{item.source} · {item.status}</p></div>
            ))}
          </article>
        )}
      </div>
      {(deliverable.unresolved.length > 0 || deliverable.compliance_notes.length > 0 || deliverable.policy_issues.length > 0) && (
        <details>
          <summary>待补与合规校验</summary>
          {[...deliverable.unresolved, ...deliverable.compliance_notes, ...deliverable.policy_issues].map((item, index) => <p key={index}>• {item}</p>)}
        </details>
      )}
    </section>
  );
}

export default function App() {
  const [session, setSession] = useState<CreationSession | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await action(message);
    setMessage("");
  }

  async function action(text: string) {
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    try {
      setSession(await sendTurn(text, session));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  const current = session?.stage ?? "brief";
  const currentIndex = stages.indexOf(current);
  const artifact = session?.artifacts[current];

  async function handleImages(files: FileList | null) {
    if (!session || !files?.length) return;
    setUploading(true);
    setError("");
    try {
      const count = await uploadImages(session.session_id, Array.from(files));
      setSession({ ...session, image_asset_count: count });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "图片上传失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main>
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="glass-panel">
        <div>
          <p className="eyebrow">AMAZON LISTING CREATION · EVIDENCE CONTROL</p>
          <h1>Listing 创作 Agent</h1>
          <p>政策、品类规则、市场研究与人工合规门驱动的完整创作流程</p>
        </div>
        <button onClick={() => setSession(null)}>新建会话</button>
      </header>

      <div className="layout">
        <aside className="glass-panel">
          <p className="kicker">WORKFLOW</p>
          <h2>创作进度</h2>
          <div className="stage-list">
            {stages.map((stage, index) => {
              const done = current === "completed" || currentIndex > index;
              return <p className={current === stage ? "current" : done ? "done" : ""} key={stage}>{done ? "✓" : current === stage ? "▶" : "○"} {labels[stage]}</p>;
            })}
          </div>
          <hr />
          <dl>
            <div><dt>状态</dt><dd>{session?.status ?? "等待 Brief"}</dd></div>
            <div><dt>站点</dt><dd>{session?.brief.marketplace || "—"}</dd></div>
            <div><dt>语言</dt><dd>{session?.brief.language || "—"}</dd></div>
            <div><dt>产品</dt><dd>{session?.brief.product_name || "—"}</dd></div>
            <div><dt>规则</dt><dd>{session?.active_rule_files.length ?? 0} 份</dd></div>
          </dl>
          {session?.brief.sensitive_category && <p className="sensitive">敏感品类 · 需要人工终审</p>}
        </aside>

        <section className="workbench glass-panel">
          <div className="message">{session?.last_message_zh || "请提供产品名称、目标站点、产品类型和规格参数；有产品/竞品 ASIN 可一并提供"}</div>
          {artifact && <details open><summary>阶段产物 · {labels[current]}</summary><pre>{JSON.stringify(artifact.payload, null, 2)}</pre></details>}
          {session?.deliverable && <DeliverablePanel deliverable={session.deliverable} />}
          {session?.image_design_plan && (
            <section className="panel-block">
              <div className="section-head"><div><p className="kicker">IMAGE SYSTEM</p><h2>主图 + 7 张辅图</h2></div></div>
              <div className="image-grid">
                {session.image_design_plan.images.map((item, index) => (
                  <article key={index} className="image-card">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <h3>{item.image}</h3>
                    <strong>{item.selling_point}</strong>
                    <p>{item.background}</p><p>{item.layout}</p><p>{item.image_copy}</p>
                  </article>
                ))}
              </div>
            </section>
          )}

          {session?.stage === "image_handoff" && (
            <section className="panel-block upload-panel">
              <div><p className="kicker">OPTIONAL ASSETS</p><h2>图片任务与素材</h2></div>
              <p>优先使用产品和竞品 ASIN 调查图片组；仅当 ASIN 无法获取图片，或产品尚未发布时上传本地素材</p>
              <div className="task-actions">
                <button type="button" onClick={() => action("图片设计")}>图片设计</button>
                <button type="button" onClick={() => action("图片优化")}>图片优化</button>
                <button type="button" onClick={() => action("图片分析")}>图片分析</button>
              </div>
              <label className="file-upload">
                <span>{uploading ? "上传中…" : `上传 JPEG / PNG / WebP（最多 8 张，已上传 ${session.image_asset_count} 张）`}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={uploading} onChange={(event) => handleImages(event.target.files)} />
              </label>
            </section>
          )}

          <form onSubmit={submit}>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={"产品: …\n站点: US\n语言: en\n产品类型: …\n父子体: parent\n媒体类目: no\n产品 ASIN: B0…\n规格: …\n竞品: B0…, B0…"} required />
            <div className="actions">
              <button type="button" onClick={() => action("认可")} disabled={!session || busy}>认可当前阶段</button>
              {session?.brief.sensitive_category && !session.human_review_confirmed && <button type="button" onClick={() => action("人工审核通过")} disabled={busy}>人工审核通过</button>}
              {session?.stage === "competitor" && <button type="button" onClick={() => action("跳过竞品")} disabled={busy}>跳过竞品</button>}
              {session?.stage === "image_handoff" && <><button type="button" onClick={() => action("不需要图片")} disabled={busy}>不需要图片</button><button type="button" onClick={() => action("需要图片")} disabled={busy}>进入图片设计</button></>}
              <button className="primary" disabled={busy}>{busy ? "处理中…" : "发送"}</button>
            </div>
            {error && <p className="error">{error}</p>}
          </form>
        </section>
      </div>
    </main>
  );
}
