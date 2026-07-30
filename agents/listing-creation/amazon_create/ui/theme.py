"""Lithos theme shared visually with the optimization agent."""

THEME_CSS = """
<style>
:root {
  --bg: #030711;
  --surface: rgba(8, 18, 35, 0.82);
  --surface-strong: rgba(10, 24, 43, 0.92);
  --text: #f4fbff;
  --soft: rgba(218, 237, 248, 0.72);
  --muted: rgba(187, 215, 231, 0.5);
  --border: rgba(125, 211, 252, 0.14);
  --border-strong: rgba(103, 232, 249, 0.34);
  --cyan: #22d3ee;
  --cyan-soft: #67e8f9;
  --danger: #fb7185;
  --warning: #fbbf24;
  --success: #22d3ee;
  --font: 'Inter', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', sans-serif;
}
html, body, .stApp, [data-testid="stAppViewContainer"] {
  color: var(--text);
  font-family: var(--font);
}
html, body { background: var(--bg); }
.stApp, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 14% 8%, rgba(8, 145, 178, 0.16), transparent 31%),
    radial-gradient(circle at 86% 82%, rgba(14, 116, 144, 0.12), transparent 36%),
    linear-gradient(145deg, #07111f 0%, #030711 48%, #07101b 100%);
}
[data-testid="stAppViewContainer"]::before {
  animation: grid-drift 28s linear infinite;
  background-image:
    linear-gradient(rgba(125, 211, 252, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(125, 211, 252, 0.025) 1px, transparent 1px);
  background-size: 56px 56px;
  content: "";
  inset: 0;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
[data-testid="stAppViewContainer"]::after {
  animation: particle-pulse 12s ease-in-out infinite alternate;
  background:
    radial-gradient(circle at 20% 38%, rgba(34, 211, 238, 0.12) 0 1px, transparent 2px),
    radial-gradient(circle at 72% 18%, rgba(165, 243, 252, 0.1) 0 1px, transparent 2px),
    radial-gradient(circle at 82% 72%, rgba(34, 211, 238, 0.09) 0 1px, transparent 2px);
  background-size: 180px 180px, 240px 240px, 210px 210px;
  content: "";
  filter: drop-shadow(0 0 7px rgba(34, 211, 238, 0.5));
  inset: 0;
  opacity: 0.68;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
@keyframes grid-drift { to { background-position: 56px 56px, 56px 56px; } }
@keyframes particle-pulse { to { opacity: 0.88; transform: scale(1.025); } }
@media (prefers-reduced-motion: reduce) {
  [data-testid="stAppViewContainer"]::before,
  [data-testid="stAppViewContainer"]::after { animation: none; }
}
[data-testid="stHeader"], [data-testid="stToolbar"] {
  background: rgba(3, 7, 17, 0.82);
  border-bottom: 1px solid rgba(125, 211, 252, 0.08);
  backdrop-filter: blur(18px);
}
[data-testid="stMainBlockContainer"] {
  max-width: 110rem;
  padding-top: 4.5rem;
  position: relative;
  z-index: 1;
}
[data-testid="stSidebar"] {
  background: rgba(5, 12, 24, 0.94);
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] > div { padding-top: 1.1rem; }
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] button,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 { font-family: var(--font); }
.material-symbols-rounded,
.material-symbols-outlined,
[data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded' !important;
}
h1 { letter-spacing: -0.03em; }
.hero {
  background: linear-gradient(145deg, rgba(12, 26, 46, 0.82), rgba(5, 13, 27, 0.68));
  border: 1px solid var(--border);
  border-radius: 22px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 24px 70px rgba(0,0,0,.22);
  margin-bottom: 1.2rem;
  padding: 1.2rem 1.35rem;
}
.hero .eyebrow {
  color: rgba(165, 243, 252, 0.86);
  font-size: .7rem;
  font-weight: 700;
  letter-spacing: .16em;
  margin: 0 0 .45rem;
}
.hero h1 { font-size: clamp(1.8rem, 4vw, 2.7rem); margin: 0; }
.hero p:last-child { color: var(--soft); margin: .5rem 0 0; }
.status-strip {
  align-items: center;
  background: rgba(34, 211, 238, 0.06);
  border: 1px solid var(--border);
  border-radius: 14px;
  color: var(--soft);
  display: flex;
  flex-wrap: wrap;
  gap: .75rem 1.4rem;
  margin-bottom: 1rem;
  padding: .7rem .9rem;
}
.status-strip strong { color: var(--cyan-soft); }
.fact-card {
  background: rgba(10, 24, 43, 0.72);
  border: 1px solid var(--border-strong);
  border-radius: 18px;
  box-shadow: 0 16px 45px rgba(0,0,0,.2);
  margin: .75rem 0 1rem;
  padding: 1rem 1.1rem;
}
.fact-card .fact-label { color: var(--cyan-soft); font-size: .78rem; font-weight: 700; letter-spacing: .08em; }
.fact-card .fact-value { font-size: 1.12rem; font-weight: 650; margin: .5rem 0; }
.fact-card .fact-reason { color: var(--soft); font-size: .88rem; line-height: 1.65; }
.confirmed-fact {
  background: rgba(34, 211, 238, 0.055);
  border: 1px solid rgba(103, 232, 249, 0.18);
  border-radius: 12px;
  margin: .35rem 0;
  padding: .55rem .65rem;
}
.confirmed-fact.missing { background: rgba(148, 163, 184, 0.06); border-color: rgba(148, 163, 184, 0.16); }
.confirmed-fact strong { color: var(--text); display: block; font-size: .86rem; }
.confirmed-fact span { color: var(--soft); display: block; font-size: .8rem; margin-top: .22rem; overflow-wrap: anywhere; }
.stButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 999px;
  font-weight: 650;
  min-height: 2.45rem;
}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, var(--cyan), var(--cyan-soft));
  border: 0;
  box-shadow: 0 8px 28px rgba(34, 211, 238, .2);
  color: #03131c;
}
.stButton > button[kind="secondary"] {
  background: rgba(125, 211, 252, 0.055);
  border: 1px solid var(--border);
  color: var(--text);
}
[data-testid="stChatMessage"] {
  background: rgba(8, 18, 35, 0.52);
  border: 1px solid rgba(125, 211, 252, 0.08);
  border-radius: 16px;
  margin-bottom: .65rem;
  padding: .25rem .45rem;
}
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] {
  color: rgba(165, 243, 252, 0.5);
  font-size: .72rem;
  margin-top: -.35rem;
  text-align: right;
}
.agent-typing {
  align-items: center;
  background: rgba(34, 211, 238, 0.07);
  border: 1px solid rgba(103, 232, 249, 0.2);
  border-radius: 14px;
  color: var(--soft);
  display: inline-flex;
  gap: .72rem;
  min-height: 2.65rem;
  padding: .62rem .82rem;
}
.agent-typing-label { font-size: .86rem; }
.typing-dots { align-items: center; display: inline-flex; gap: .28rem; }
.typing-dots i {
  animation: typing-bounce 1.05s ease-in-out infinite;
  background: var(--cyan-soft);
  border-radius: 50%;
  box-shadow: 0 0 8px rgba(103, 232, 249, .55);
  display: block;
  height: .38rem;
  width: .38rem;
}
.typing-dots i:nth-child(2) { animation-delay: .14s; }
.typing-dots i:nth-child(3) { animation-delay: .28s; }
@keyframes typing-bounce {
  0%, 60%, 100% { opacity: .35; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-.28rem); }
}
[data-testid="stChatInput"] { background: rgba(7, 20, 38, 0.92); border-color: var(--border-strong); }
[data-testid="stExpander"] {
  background: rgba(8, 18, 35, 0.5);
  border: 1px solid var(--border);
  border-radius: 14px;
}
.stAlert { border-radius: 14px; }
code { color: var(--cyan-soft) !important; }
@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"] { padding-top: 4rem; }
  .status-strip { align-items: flex-start; flex-direction: column; gap: .35rem; }
}
@media (prefers-reduced-motion: reduce) {
  .typing-dots i { animation: none; opacity: .75; }
}
</style>
"""

__all__ = ["THEME_CSS"]
