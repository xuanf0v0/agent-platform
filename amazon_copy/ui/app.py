"""Single-purpose Streamlit UI for Amazon listing copy optimization.

Unified dark Lithos visual system (aligned with .streamlit/config.toml):
near-black canvas, Inter UI (CJK-safe), orange pill CTA, glass
cards. No fake HTML wrappers around Streamlit widgets (avoids layout drift).
Optimization logic is unchanged.
"""

from __future__ import annotations

# Streamlit render calls intentionally return unused DeltaGenerator handles.
# pyright: reportUnusedCallResult=false
import re
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING

import streamlit as st
from pydantic import JsonValue, TypeAdapter, ValidationError

import amazon_copy.simple_optimizer as optimizer_service
from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticOptimizationResult,
    AutomaticResearchCache,
    AwaitingApproval,
    ClarificationAnswer,
    CompletedOptimization,
    FailedOptimization,
    NeedsClarification,
    ProductIdentity,
)
from amazon_copy.automatic_research import secure_research_cache
from amazon_copy.input_security import (
    MAX_LISTING_INPUT_CHARS,
    InputSecurityError,
    require_clarification_input,
    require_listing_input,
)
from amazon_copy.mcp.security import sanitize_mcp_text
from amazon_copy.ui.audit_pipeline import layers_from_session
from amazon_copy.ui.specialized import (
    RenderableOptimization,
    render_clarification,
    render_specialized_evidence,
)
from amazon_copy.ui.view_models import (
    format_layer_sections,
    format_mcp_research_sections,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from amazon_copy.review.diagnosis_models import ListingDiagnosisReport
    from amazon_copy.review.models import ListingReviewReport
    from streamlit.delta_generator import DeltaGenerator

# Tokens mirror .streamlit/config.toml — keep hex values in sync.
# CJK rule: never apply Latin-only italic / negative tracking to Chinese titles.
_THEME_CSS = """
<style>
:root {
  --lithos-bg: #000000;
  --lithos-surface: #141414;
  --lithos-surface-2: #1a1a1a;
  --lithos-text: #ffffff;
  --lithos-text-soft: rgba(255, 255, 255, 0.72);
  --lithos-text-muted: rgba(255, 255, 255, 0.72);
  --lithos-border: rgba(255, 255, 255, 0.14);
  --lithos-border-strong: rgba(255, 255, 255, 0.22);
  --lithos-cta: #e8702a;
  --lithos-cta-hover: #d2611f;
  --lithos-cta-active: #c45618;
  --lithos-cta-text: #000000;
  --lithos-toolbar-bg: rgba(0, 0, 0, 0.94);
  --lithos-eyebrow-bg: rgba(255, 255, 255, 0.12);
  --lithos-eyebrow-border: rgba(255, 255, 255, 0.28);
  --lithos-eyebrow-text: rgba(255, 255, 255, 0.85);
  --lithos-label-text: rgba(255, 255, 255, 0.85);
  --lithos-placeholder-text: rgba(255, 255, 255, 0.62);
  --lithos-cta-shadow: 0 4px 16px rgba(232, 112, 42, 0.28);
  --lithos-cta-shadow-hover: 0 6px 20px rgba(232, 112, 42, 0.38);
  --lithos-disabled-bg: rgba(255, 255, 255, 0.08);
  --lithos-disabled-text: rgba(255, 255, 255, 0.35);
  --lithos-secondary-bg: rgba(255, 255, 255, 0.06);
  --lithos-secondary-text: rgba(255, 255, 255, 0.9);
  --lithos-secondary-hover-border: rgba(255, 255, 255, 0.4);
  --lithos-expander-text: rgba(255, 255, 255, 0.92);
  --lithos-status-gradient: linear-gradient(
    135deg,
    rgba(232, 112, 42, 0.08),
    rgba(20, 20, 20, 0.95)
  );
  --lithos-success-strong: #22c55e;
  --lithos-success-subtle: rgba(34, 197, 94, 0.06);
  --lithos-error-strong: #ef4444;
  --lithos-error-subtle: rgba(239, 68, 68, 0.06);
  --lithos-warning-strong: #eab308;
  --lithos-info-strong: #3b82f6;
  --lithos-toast-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  --lithos-transparent: transparent;
  --lithos-radius: 16px;
  --lithos-radius-lg: 20px;
  --lithos-radius-pill: 9999px;
  --lithos-radius-control: 12px;
  --lithos-radius-textarea: 14px;
  --lithos-border-accent-width: 3px;
  --lithos-font-eyebrow: 0.7rem;
  --lithos-font-body: 0.95rem;
  --lithos-font-secondary: 0.85rem;
  --lithos-font-section: 0.78rem;
  --lithos-font-heading: 1.15rem;
  --lithos-font-title: clamp(1.85rem, 5vw, 2.75rem);
  --lithos-line-tight: 1.4;
  --lithos-line-body: 1.7;
  --lithos-line-caption: 1.55;
  --lithos-line-icon: 1;
  --lithos-line-title: 1.25;
  --lithos-line-heading: 1.35;
  --lithos-line-expander: 1.45;
  --lithos-line-status: 1.5;
  --lithos-space-none: 0;
  --lithos-space-main-top: 5rem;
  --lithos-space-main-bottom: 3rem;
  --lithos-space-xxs: 0.35rem;
  --lithos-space-xs: 0.38rem;
  --lithos-space-sm: 0.45rem;
  --lithos-space-md: 0.5rem;
  --lithos-space-lg: 0.55rem;
  --lithos-space-xl: 0.65rem;
  --lithos-space-2xl: 0.7rem;
  --lithos-space-3xl: 0.75rem;
  --lithos-space-4xl: 1rem;
  --lithos-space-5xl: 1.2rem;
  --lithos-space-6xl: 1.25rem;
  --lithos-space-7xl: 1.35rem;
  --lithos-space-8xl: 1.5rem;
  --lithos-space-9xl: 2rem;
  --lithos-gap-inline: 0.35rem;
  --lithos-gap-button: 6px;
  --lithos-glass: rgba(255, 255, 255, 0.045);
  --lithos-glass-strong: rgba(255, 255, 255, 0.06);
  --lithos-focus-ring: 0 0 0 1px #e8702a, 0 0 24px rgba(232, 112, 42, 0.18);
  --lithos-font-ui: 'Inter', 'Microsoft YaHei', 'PingFang SC',
    'Noto Sans SC', 'Segoe UI', sans-serif;
  --lithos-success-bg: rgba(34, 197, 94, 0.12);
  --lithos-success-border: rgba(34, 197, 94, 0.35);
  --lithos-error-bg: rgba(239, 68, 68, 0.12);
  --lithos-error-border: rgba(239, 68, 68, 0.4);
  --lithos-warning-bg: rgba(234, 179, 8, 0.12);
  --lithos-warning-border: rgba(234, 179, 8, 0.4);
  --lithos-info-bg: rgba(59, 130, 246, 0.12);
  --lithos-info-border: rgba(59, 130, 246, 0.35);
}

/* ---------- Dark canvas (align with config.toml) ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  background-color: var(--lithos-bg);
  color: var(--lithos-text);
  letter-spacing: normal;
  font-family: var(--lithos-font-ui);
}
[data-testid="stHeader"], [data-testid="stToolbar"] {
  background: var(--lithos-toolbar-bg);
  backdrop-filter: blur(12px);
}
[data-testid="stMainBlockContainer"] {
  padding-top: var(--lithos-space-main-top);
  padding-bottom: var(--lithos-space-main-bottom);
  max-width: 110rem;
}
[data-testid="stBottomBlockContainer"] {
  width: min(58rem, calc(100% - 2rem)) !important;
  max-width: 58rem !important;
  margin-left: max(1rem, calc((100vw - 110rem) / 2)) !important;
  margin-right: auto !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
  word-break: auto-phrase;
  overflow-wrap: break-word;
  line-break: strict;
}
.lithos-no-break {
  display: inline-block;
  white-space: nowrap !important;
}
.lithos-confirm-copy,
.lithos-confirm-question,
.lithos-confirm-footer {
  line-height: var(--lithos-line-body);
}
.lithos-confirm-question,
.lithos-confirm-footer {
  font-weight: 600;
}
.lithos-confirm-evidence {
  color: var(--lithos-text-muted);
  font-size: var(--lithos-font-secondary);
  line-height: var(--lithos-line-caption);
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {
    padding-bottom: 9rem;
  }
}
@media (max-width: 900px) {
  [data-testid="stBottomBlockContainer"] {
    margin-inline: auto !important;
  }
}
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] button,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2 {
  font-family: var(--lithos-font-ui);
  letter-spacing: normal;
}

/* Streamlit renders widget icons as Material Symbol ligatures. Keep those spans
   out of the UI font override so labels and icons occupy separate glyph space. */
.material-symbols-rounded,
.material-symbols-outlined,
.material-symbols-sharp,
[class*="material-symbols"],
[data-testid="stIconMaterial"],
[data-testid="stAlertDynamicIcon"],
[data-testid="stAppViewContainer"] span[class*="material-symbols"],
[data-testid="stAppViewContainer"] span[data-testid="stIconMaterial"],
[data-testid="stAppViewContainer"] span[data-testid="stAlertDynamicIcon"] {
  font-family: 'Material Symbols Rounded' !important;
  font-style: normal !important;
  font-weight: normal !important;
  letter-spacing: normal !important;
  line-height: var(--lithos-line-icon) !important;
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
  color: var(--lithos-text-muted) !important;
  opacity: 1 !important;
  line-height: var(--lithos-line-caption) !important;
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* ---------- Hero header (CJK-safe: no italic / no negative tracking) ---------- */
.lithos-eyebrow {
  display: inline-flex;
  flex-wrap: wrap;
  max-width: 100%;
  box-sizing: border-box;
  gap: var(--lithos-space-none) var(--lithos-gap-inline);
  background: var(--lithos-eyebrow-bg);
  border: 1px solid var(--lithos-eyebrow-border);
  border-radius: var(--lithos-radius-pill);
  padding: var(--lithos-space-xs) var(--lithos-space-4xl);
  font-size: var(--lithos-font-eyebrow);
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--lithos-eyebrow-text);
  margin: var(--lithos-space-none) var(--lithos-space-none) var(--lithos-space-md);
  line-height: var(--lithos-line-tight);
}
.lithos-eyebrow-clause { white-space: nowrap; }
.lithos-title {
  display: block;
  font-family: var(--lithos-font-ui);
  font-style: normal;
  font-weight: 600;
  font-size: var(--lithos-font-title);
  line-height: var(--lithos-line-title);
  letter-spacing: 0.02em;
  color: var(--lithos-text);
  margin: var(--lithos-space-md) var(--lithos-space-none) var(--lithos-space-xl);
  word-break: keep-all;
  overflow-wrap: break-word;
}
.lithos-sub {
  display: block;
  color: var(--lithos-text-soft);
  font-size: var(--lithos-font-body);
  line-height: var(--lithos-line-body);
  max-width: 36rem;
  margin: var(--lithos-space-none) var(--lithos-space-none) var(--lithos-space-8xl);
  word-break: keep-all;
  overflow-wrap: normal;
}
.lithos-sub-unit { white-space: nowrap; }

/* Section labels (result / audit) */
.lithos-section-label {
  display: block;
  font-family: var(--lithos-font-ui);
  font-size: var(--lithos-font-section);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--lithos-text-muted);
  margin: var(--lithos-space-8xl) var(--lithos-space-none) var(--lithos-space-lg);
  line-height: var(--lithos-line-tight);
}

/* ---------- Glass form card ---------- */
[data-testid="stForm"] {
  background: var(--lithos-glass);
  border: 1px solid var(--lithos-border);
  border-radius: var(--lithos-radius-lg);
  padding: var(--lithos-space-5xl) var(--lithos-space-5xl) var(--lithos-space-7xl);
  margin-bottom: var(--lithos-space-3xl);
}

/* ---------- Text areas ---------- */
[data-testid="stTextArea"] {
  width: 100%;
}
[data-testid="stTextArea"] label {
  display: block;
  margin-bottom: var(--lithos-space-xxs);
}
[data-testid="stTextArea"] label p {
  color: var(--lithos-label-text) !important;
  font-weight: 500;
  line-height: var(--lithos-line-tight) !important;
  letter-spacing: normal !important;
}
[data-testid="stTextArea"] textarea {
  background: var(--lithos-glass-strong) !important;
  color: var(--lithos-text) !important;
  border: 1px solid var(--lithos-border-strong) !important;
  border-radius: var(--lithos-radius-textarea) !important;
  caret-color: var(--lithos-cta);
  line-height: var(--lithos-line-caption) !important;
  letter-spacing: normal !important;
  font-family: var(--lithos-font-ui) !important;
  transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
}
[data-testid="stTextArea"] textarea::placeholder {
  color: var(--lithos-placeholder-text) !important;
  letter-spacing: normal !important;
}
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--lithos-cta) !important;
  box-shadow: var(--lithos-focus-ring) !important;
  outline: none !important;
}

/* ---------- Text inputs / select ---------- */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] input,
[data-testid="stSelectbox"] div[data-baseweb="select"] {
  background: var(--lithos-glass-strong) !important;
  color: var(--lithos-text) !important;
  border: 1px solid var(--lithos-border-strong) !important;
  border-radius: var(--lithos-radius-control) !important;
  caret-color: var(--lithos-cta);
  letter-spacing: normal !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stSelectbox"] input:focus {
  border-color: var(--lithos-cta) !important;
  box-shadow: var(--lithos-focus-ring) !important;
}
[data-testid="stTextInput"] label p,
[data-testid="stSelectbox"] label p {
  color: var(--lithos-label-text) !important;
  font-weight: 500;
  letter-spacing: normal !important;
}

/* ========== BUTTON SYSTEM ========== */

/* Primary CTA — orange pill (readable on black) */
[data-testid="stFormSubmitButton"] button,
button[kind="primary"] {
  background: var(--lithos-cta) !important;
  color: var(--lithos-cta-text) !important;
  border: 1px solid var(--lithos-transparent) !important;
  border-radius: var(--lithos-radius-pill) !important;
  font-size: var(--lithos-font-body) !important;
  font-weight: 600 !important;
  line-height: var(--lithos-line-tight) !important;
  letter-spacing: normal !important;
  padding: var(--lithos-space-2xl) var(--lithos-space-9xl) !important;
  box-shadow: var(--lithos-cta-shadow) !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: var(--lithos-gap-button) !important;
  white-space: nowrap !important;
  transition: background 0.2s ease, box-shadow 0.2s ease !important;
}
[data-testid="stFormSubmitButton"] button:hover,
button[kind="primary"]:hover {
  background: var(--lithos-cta-hover) !important;
  box-shadow: var(--lithos-cta-shadow-hover) !important;
  transform: none !important;
}
[data-testid="stFormSubmitButton"] button:active,
button[kind="primary"]:active {
  background: var(--lithos-cta-active) !important;
  transform: none !important;
}
[data-testid="stFormSubmitButton"] button:focus-visible,
button[kind="primary"]:focus-visible {
  outline: none !important;
  box-shadow: var(--lithos-focus-ring) !important;
}
[data-testid="stFormSubmitButton"] button:disabled,
button[kind="primary"]:disabled {
  background: var(--lithos-disabled-bg) !important;
  color: var(--lithos-disabled-text) !important;
  border-color: var(--lithos-transparent) !important;
  box-shadow: none !important;
  cursor: not-allowed;
}

/* Secondary */
button[kind="secondary"],
[data-testid="stBaseButton-secondary"] button,
.stDownloadButton button {
  background: var(--lithos-secondary-bg) !important;
  color: var(--lithos-secondary-text) !important;
  border: 1px solid var(--lithos-border-strong) !important;
  border-radius: var(--lithos-radius-pill) !important;
  font-size: var(--lithos-font-secondary) !important;
  font-weight: 500 !important;
  letter-spacing: normal !important;
  padding: var(--lithos-space-sm) var(--lithos-space-5xl) !important;
  white-space: nowrap !important;
}
button[kind="secondary"]:hover,
[data-testid="stBaseButton-secondary"] button:hover,
.stDownloadButton button:hover {
  background: var(--lithos-eyebrow-bg) !important;
  border-color: var(--lithos-secondary-hover-border) !important;
  color: var(--lithos-text) !important;
  transform: none !important;
}

/* ---------- Headings / audit panel ---------- */
[data-testid="stMarkdownContainer"] h2 {
  font-family: var(--lithos-font-ui);
  font-style: normal;
  font-weight: 600;
  font-size: var(--lithos-font-heading);
  letter-spacing: 0.02em;
  line-height: var(--lithos-line-heading);
  color: var(--lithos-text);
  margin: var(--lithos-space-7xl) var(--lithos-space-none) var(--lithos-space-xl);
  word-break: keep-all;
}
h2.lithos-section-label {
  font-family: var(--lithos-font-ui);
  font-style: normal;
  font-size: var(--lithos-font-section);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--lithos-text-muted);
  line-height: var(--lithos-line-tight);
  margin: var(--lithos-space-8xl) var(--lithos-space-none) var(--lithos-space-lg);
}
[data-testid="stMarkdownContainer"] h3 {
  font-family: var(--lithos-font-ui);
  font-style: normal;
  font-weight: 600;
  font-size: var(--lithos-font-heading);
  letter-spacing: 0.02em;
  line-height: var(--lithos-line-heading);
  color: var(--lithos-text);
  margin: var(--lithos-space-7xl) var(--lithos-space-none) var(--lithos-space-xl);
  word-break: keep-all;
}
[data-testid="stExpander"] {
  background: var(--lithos-glass);
  border: 1px solid var(--lithos-border);
  border-radius: var(--lithos-radius);
  overflow: hidden;
  margin-bottom: var(--lithos-space-md);
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
  color: var(--lithos-expander-text) !important;
  font-family: var(--lithos-font-ui) !important;
  letter-spacing: normal !important;
  line-height: var(--lithos-line-expander) !important;
  word-break: break-word;
}
[data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded' !important;
  font-style: normal !important;
  font-weight: normal !important;
  line-height: var(--lithos-line-icon) !important;
}
[data-testid="stExpander"] details {
  background: transparent;
}

/* ---------- Status / alerts on dark ---------- */
[data-testid="stStatusWidget"] {
  background: var(--lithos-status-gradient) !important;
  border: 1px solid var(--lithos-border) !important;
  border-left: 3px solid var(--lithos-cta) !important;
  border-radius: var(--lithos-radius) !important;
  padding: var(--lithos-space-3xl) var(--lithos-space-4xl) !important;
}
[data-testid="stStatusWidget"] p,
[data-testid="stStatusWidget"] span {
  letter-spacing: normal !important;
  line-height: var(--lithos-line-status) !important;
}
[data-testid="stStatusWidget"][data-state="complete"] {
  border-left-color: var(--lithos-success-strong) !important;
  background: var(--lithos-success-subtle) !important;
}
[data-testid="stStatusWidget"][data-state="error"] {
  border-left-color: var(--lithos-error-strong) !important;
  background: var(--lithos-error-subtle) !important;
}

[data-testid="stAlert"] {
  border-radius: var(--lithos-radius) !important;
  border: 1px solid var(--lithos-border) !important;
}
div[data-testid="stAlert"][kind="error"] {
  background: var(--lithos-error-bg) !important;
  border-color: var(--lithos-error-border) !important;
  border-left: var(--lithos-border-accent-width) solid var(--lithos-error-strong) !important;
}
div[data-testid="stAlert"][kind="success"] {
  background: var(--lithos-success-bg) !important;
  border-color: var(--lithos-success-border) !important;
  border-left: var(--lithos-border-accent-width) solid var(--lithos-success-strong) !important;
}
div[data-testid="stAlert"][kind="warning"] {
  background: var(--lithos-warning-bg) !important;
  border-color: var(--lithos-warning-border) !important;
  border-left: var(--lithos-border-accent-width) solid var(--lithos-warning-strong) !important;
}
div[data-testid="stAlert"][kind="info"] {
  background: var(--lithos-info-bg) !important;
  border-color: var(--lithos-info-border) !important;
  border-left: var(--lithos-border-accent-width) solid var(--lithos-info-strong) !important;
}
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
  color: var(--lithos-text-soft) !important;
  letter-spacing: normal !important;
  line-height: var(--lithos-line-caption) !important;
}
hr {
  border: none;
  border-top: 1px solid var(--lithos-border);
  margin: var(--lithos-space-6xl) var(--lithos-space-none);
}

[data-testid="stToast"] {
  background: var(--lithos-surface) !important;
  border: 1px solid var(--lithos-border) !important;
  border-left: var(--lithos-border-accent-width) solid var(--lithos-success-strong) !important;
  border-radius: var(--lithos-radius) !important;
  color: var(--lithos-text) !important;
  box-shadow: var(--lithos-toast-shadow) !important;
}
</style>
"""


def _inject_theme_styles() -> None:
    """Apply the unified dark Lithos theme to Streamlit chrome."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


_RESULT_KEY = "automatic_workflow_result"
_SOURCE_FINGERPRINT_KEY = "automatic_source_fingerprint"
_SOURCE_WIDGET_KEY = "source_listing"
_SOURCE_TEXT_KEY = "conversation_source_text"
_PROGRESS_STEP_KEY = "automatic_progress_step"
_PROGRESS_LABEL_KEY = "automatic_progress_label"
_QUALITY_ROUNDS_KEY = "automatic_quality_rounds"
_CLARIFICATION_REPLIES_KEY = "conversation_clarification_replies"
_OPTIMIZED_WIDGET_KEY = "optimized_listing_result"
_ASIN_KEY = "optional_product_asin"
_SKIP_APPROVAL_KEY = "skip_approval_direct_optimize"
_APPROVAL_TOKEN_KEY = "stage1_approval_token"
_ASIN_RE = re.compile(r"^[A-Za-z0-9]{10}$")
_RESULT_ADAPTER: TypeAdapter[AutomaticOptimizationResult] = TypeAdapter(AutomaticOptimizationResult)
_STORED_RESULT_ADAPTER: TypeAdapter[JsonValue | AutomaticOptimizationResult] = TypeAdapter(
    JsonValue | AutomaticOptimizationResult
)
_SOURCE_TEXT_ADAPTER: TypeAdapter[str] = TypeAdapter(str)
_PRIVATE_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_SECRET_LIKE_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]+|(?:api[_-]?key|token|secret)[=:]\S+|https?://\S+)",
    re.IGNORECASE,
)
_RELEASE_LABELS = {
    "release": "可发布",
    "clarify": "需澄清",
    "block": "禁止发布",
}


def _safe_error_message(exc: BaseException) -> str:
    error_name = type(exc).__name__.casefold()
    if "timeout" in error_name:
        return "模型服务响应超时（单次60秒，已重试1次），请稍后重试。"
    if "connection" in error_name or "connect" in error_name:
        return "无法连接模型服务，请检查网络、代理或模型服务地址后重试。"
    if "ratelimit" in error_name or "rate_limit" in error_name:
        return "模型服务触发限流或额度不足，请等待额度恢复后重试。"
    if "authentication" in error_name or "permission" in error_name:
        return "模型服务鉴权失败，请检查 API Key 与模型访问权限。"
    if "badrequest" in error_name:
        return "模型服务拒绝了请求，请检查模型名称或服务配置。"
    if "config" in error_name:
        return "模型服务配置不完整，请检查 API Key、模型名称和服务地址。"
    raw_text = str(exc)
    text = _sanitize_sensitive_text(exc).strip()
    if not text:
        return "自动优化未完成，请稍后重试。"
    if _SECRET_LIKE_RE.search(raw_text):
        return "自动优化未完成：服务配置或凭据异常，请稍后重试。"
    summary = " ".join(text.split())[:240]
    return f"运行异常（{type(exc).__name__}）：{summary}"


def _sanitize_sensitive_text(value: str | BaseException) -> str:
    text = value if isinstance(value, str) else str(value)
    return _PRIVATE_URL_RE.sub("[已隐藏链接]", sanitize_mcp_text(text))


def _sanitize_research_cache(cache: AutomaticResearchCache) -> AutomaticResearchCache:
    return secure_research_cache(cache)


def _result_attr(result: object, name: str, default: object = None) -> object:
    """Read result fields safely across Streamlit hot-reload class mismatches."""
    return getattr(result, name, default)


def _sanitize_result_cache(result: AutomaticOptimizationResult) -> AutomaticOptimizationResult:
    cache = _result_attr(result, "research_cache")
    if cache is None:
        return result
    if not isinstance(cache, AutomaticResearchCache):
        return result
    secured = _sanitize_research_cache(cache)
    updates: dict[str, object] = {"research_cache": secured}
    evidence = _result_attr(result, "evidence_bundle")
    if evidence is not None and hasattr(evidence, "model_copy"):
        updates["evidence_bundle"] = evidence.model_copy(update={"research": secured.bundle})
    try:
        return result.model_copy(update=updates)
    except Exception:  # noqa: BLE001 - legacy result objects must not crash the UI
        return result


def _clear_workflow_state() -> None:
    explicit = {
        _RESULT_KEY,
        _SOURCE_FINGERPRINT_KEY,
        _OPTIMIZED_WIDGET_KEY,
        _SOURCE_TEXT_KEY,
        _CLARIFICATION_REPLIES_KEY,
        _APPROVAL_TOKEN_KEY,
        "automatic_workflow_status",
        _PROGRESS_STEP_KEY,
        _PROGRESS_LABEL_KEY,
        _QUALITY_ROUNDS_KEY,
        "automatic_retry",
        "audit_layers",
        "mcp_research",
        "research_cache",
    }
    dynamic = {
        key
        for raw_key in list(st.session_state)
        if isinstance(raw_key, str)
        for key in (raw_key,)
        if key.startswith(("clarification_action_", "clarification_value_"))
    }
    for key in explicit | dynamic:
        st.session_state.pop(key, None)


def _sync_source_fingerprint(source_text: str) -> None:
    current = source_fingerprint(source_text)
    previous = st.session_state.get(_SOURCE_FINGERPRINT_KEY)
    if isinstance(previous, str) and previous != current:
        _clear_workflow_state()
    st.session_state[_SOURCE_FINGERPRINT_KEY] = current


def _result_payload(raw: object) -> object | None:
    """Normalize session/API payloads to JSON-shaped data for the current schema."""
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        try:
            return raw.model_dump(mode="json")  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 - legacy session objects must not crash the UI
            return None
    return raw


def _coerce_result(raw: JsonValue | AutomaticOptimizationResult) -> AutomaticOptimizationResult:
    # Always re-validate through the current schema so session payloads from
    # older app versions (missing diagnosis_report, etc.) upgrade safely.
    payload = _result_payload(raw)
    try:
        if payload is None:
            raise TypeError("empty optimization payload")
        result: AutomaticOptimizationResult = _RESULT_ADAPTER.validate_python(payload)
    except (ValidationError, TypeError, ValueError):
        result = FailedOptimization(
            code="optimization_failed",
            message="自动优化返回了无法识别的结果，请稍后重试。",
        )
    if isinstance(result, FailedOptimization):
        match result.code:
            case "invalid_source":
                message = "Listing 输入过长或格式无效。"
            case "optimization_failed":
                raw_message = result.message.strip()
                if _SECRET_LIKE_RE.search(raw_message):
                    message = "自动优化未完成：服务配置或凭据异常，请稍后重试。"
                else:
                    message = (
                        _sanitize_sensitive_text(raw_message) or "自动优化未完成，请稍后重试。"
                    )
            case "postflight_blocked":
                message = "优化后复核 BLOCK，已禁止进入复制区。"
            case "stale_approval":
                message = "诊断审批已失效：请重新分析当前 Listing 后再生成上传稿。"
        return _sanitize_result_cache(result.model_copy(update={"message": message}))
    if isinstance(result, CompletedOptimization) and (
        result.postflight_review.status == "BLOCK" or not result.postflight_review.can_optimize
    ):
        return _sanitize_result_cache(
            FailedOptimization(
                code="postflight_blocked",
                message="优化后复核 BLOCK，已禁止进入复制区。",
                source_review=result.source_review,
                postflight_review=result.postflight_review,
                rule_context=result.rule_context,
                evidence_bundle=result.evidence_bundle,
                research_cache=result.research_cache,
                cache_reused=result.cache_reused,
                specialized_rule_cache=result.specialized_rule_cache,
                specialized_cache_reused=result.specialized_cache_reused,
                specialized_rule_guidance=result.specialized_rule_guidance,
                diagnosis_report=getattr(result, "diagnosis_report", None),
            )
        )
    return _sanitize_result_cache(result)


def _stored_result() -> AutomaticOptimizationResult | None:
    stored_value = st.session_state.get(_RESULT_KEY)
    if stored_value is None:
        return None
    # Prefer plain dict session payloads; object instances can be stale after reload.
    if not isinstance(stored_value, dict):
        payload = _result_payload(stored_value)
        if not isinstance(payload, dict):
            st.session_state.pop(_RESULT_KEY, None)
            return None
        stored_value = payload
        st.session_state[_RESULT_KEY] = payload
    try:
        result = _coerce_result(stored_value)
    except (ValidationError, AttributeError, TypeError, ValueError):
        st.session_state.pop(_RESULT_KEY, None)
        return None
    # Drop results that cannot expose diagnosis safely (stale class after hot reload).
    if not hasattr(result, "diagnosis_report"):
        st.session_state.pop(_RESULT_KEY, None)
        return None
    return result


def _store_result(result: AutomaticOptimizationResult) -> None:
    try:
        payload = result.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        payload = _result_payload(result)
    if not isinstance(payload, dict):
        # Never fail silently: surface a safe terminal result.
        payload = FailedOptimization(
            code="optimization_failed",
            message="结果无法写入会话，请点击新建对话后重试。",
        ).model_dump(mode="json")
    st.session_state[_RESULT_KEY] = payload
    status = str(payload.get("status") or _result_attr(result, "status", ""))
    st.session_state["automatic_workflow_status"] = status
    if status == "awaiting_approval":
        st.session_state[_PROGRESS_STEP_KEY] = 5
        st.session_state[_PROGRESS_LABEL_KEY] = "Stage 1 完成，等待生成上传稿"
        token = payload.get("approval_token") or _result_attr(result, "approval_token", "")
        if isinstance(token, str) and token:
            st.session_state[_APPROVAL_TOKEN_KEY] = token
        st.session_state.pop(_OPTIMIZED_WIDGET_KEY, None)
    elif status == "completed":
        st.session_state[_PROGRESS_STEP_KEY] = len(_WORKFLOW_STEPS)
        st.session_state[_PROGRESS_LABEL_KEY] = "全部规则与发布门禁通过"
        rendered = payload.get("rendered_text") or _result_attr(result, "rendered_text", "")
        if isinstance(rendered, str) and rendered:
            st.session_state[_OPTIMIZED_WIDGET_KEY] = rendered
        st.session_state.pop(_APPROVAL_TOKEN_KEY, None)
    else:
        if status == "needs_clarification":
            st.session_state[_PROGRESS_LABEL_KEY] = "等待补充或确认事实"
        elif status == "failed":
            st.session_state[_PROGRESS_LABEL_KEY] = "流程停止，请查看错误信息"
        st.session_state.pop(_OPTIMIZED_WIDGET_KEY, None)
        if status != "needs_clarification":
            st.session_state.pop(_APPROVAL_TOKEN_KEY, None)


def _optional_identity() -> ProductIdentity | None:
    """Build display-only identity from the optional ASIN field (never guessed)."""
    raw = st.session_state.get(_ASIN_KEY, "")
    if not isinstance(raw, str):
        return None
    asin = raw.strip().upper()
    if not asin:
        return None
    if not _ASIN_RE.fullmatch(asin):
        return None
    return ProductIdentity(asin=asin)


def _skip_approval_checked() -> bool:
    return bool(st.session_state.get(_SKIP_APPROVAL_KEY, False))


_WORKFLOW_STEPS = (
    "解析 Listing",
    "市场研究与关键词",
    "产品路由与专项规则",
    "事实证据与冲突检查",
    "Stage 1 综合诊断",
    "生成或按失败规则重写",
    "语法、语义与结构诊断",
    "美国本土化审核 Agent",
    "确定性安全与发布门禁",
)


def _result_progress_step(result: AutomaticOptimizationResult | None) -> int:
    stored = st.session_state.get(_PROGRESS_STEP_KEY, 0)
    step = stored if isinstance(stored, int) else 0
    if result is None:
        return step
    status = str(_result_attr(result, "status", ""))
    if status == "awaiting_approval":
        return max(step, 5)
    if status == "completed":
        return len(_WORKFLOW_STEPS)
    return step


def _render_runtime_panel(
    slot: DeltaGenerator,
    result: AutomaticOptimizationResult | None,
) -> None:
    """Render the live execution layer in the right-hand workspace rail."""
    current = _result_progress_step(result)
    active_label = str(st.session_state.get(_PROGRESS_LABEL_KEY, "等待 Listing 输入"))
    with slot.container(border=True, gap="small"):
        st.markdown("### 实时运行层级")
        st.caption(active_label)
        st.progress(current / len(_WORKFLOW_STEPS))
        for index, label in enumerate(_WORKFLOW_STEPS, start=1):
            if index < current:
                icon = ":material/check_circle:"
                tone = "green"
            elif index == current:
                icon = ":material/progress_activity:"
                tone = "orange"
            else:
                icon = ":material/radio_button_unchecked:"
                tone = "gray"
            st.badge(label, icon=icon, color=tone)


def _progress_callback(
    slot: DeltaGenerator,
    result: AutomaticOptimizationResult | None,
) -> Callable[[str, int, int], None]:
    def update(label: str, step: int, total: int) -> None:
        del total
        st.session_state[_PROGRESS_LABEL_KEY] = label
        st.session_state[_PROGRESS_STEP_KEY] = step
        _render_runtime_panel(slot, result)

    return update


def _render_quality_rounds_panel(slot: DeltaGenerator) -> None:
    """Render quality rounds in a separate far-right workspace rail."""
    raw_rounds = st.session_state.get(_QUALITY_ROUNDS_KEY, ())
    rounds = raw_rounds if isinstance(raw_rounds, (list, tuple)) else ()
    with slot.container(border=True, gap="small"):
        st.markdown("### 未通过原因")
        if not rounds:
            st.caption("进入语法与本土化循环后，将在这里实时显示每轮结果。")
            return
        for entry in rounds:
            if not isinstance(entry, dict):
                continue
            attempt = int(entry.get("attempt", 0))
            total = int(entry.get("total", 0))
            passed = bool(entry.get("passed", False))
            raw_reasons = entry.get("reasons", ())
            reasons = raw_reasons if isinstance(raw_reasons, (list, tuple)) else ()
            if passed:
                st.success(
                    f"第 {attempt}/{total} 轮：全部通过",
                    icon=":material/check_circle:",
                )
                continue
            with st.expander(
                f"第 {attempt}/{total} 轮 · {len(reasons)} 项未通过",
                expanded=True,
                icon=":material/error:",
            ):
                for reason in reasons:
                    st.text(f"• {reason}")


def _quality_callback(
    slot: DeltaGenerator,
) -> Callable[[int, int, tuple[str, ...], bool], None]:
    def update(attempt: int, total: int, reasons: tuple[str, ...], passed: bool) -> None:
        raw_rounds = st.session_state.get(_QUALITY_ROUNDS_KEY, ())
        rounds = list(raw_rounds) if isinstance(raw_rounds, (list, tuple)) else []
        rounds = [
            item
            for item in rounds
            if isinstance(item, dict) and item.get("attempt") != attempt
        ]
        rounds.append(
            {
                "attempt": attempt,
                "total": total,
                "reasons": tuple(reasons),
                "passed": passed,
            }
        )
        rounds.sort(key=lambda item: int(item.get("attempt", 0)))
        st.session_state[_QUALITY_ROUNDS_KEY] = tuple(rounds)
        _render_quality_rounds_panel(slot)

    return update


def _invoke_automatic(
    source_text: str,
    context: AutomaticOptimizationContext | None = None,
    *,
    spinner_text: str = "正在审核并诊断…（约 15–60 秒）",
    progress_callback: Callable[[str, int, int], None] | None = None,
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None,
) -> AutomaticOptimizationResult:
    st.session_state[_PROGRESS_STEP_KEY] = 0
    st.session_state[_PROGRESS_LABEL_KEY] = "初始化模型服务"
    st.session_state[_QUALITY_ROUNDS_KEY] = ()
    if progress_callback is not None:
        progress_callback("初始化模型服务", 0, len(_WORKFLOW_STEPS))
    identity = _optional_identity()
    base_updates: dict[str, object] = {
        "auto_resolve_unverified": True,
        "identity": identity,
    }
    if context is None:
        automatic_context = AutomaticOptimizationContext(
            auto_resolve_unverified=True,
            skip_approval=_skip_approval_checked(),
            mode="optimize" if _skip_approval_checked() else "diagnose",
            identity=identity,
        )
    else:
        automatic_context = context.model_copy(update=base_updates)
    try:
        with st.spinner(spinner_text):
            run = optimizer_service.run_automatic_optimization
            call_kwargs: dict[str, object] = {"context": automatic_context}
            if "dependencies" in inspect.signature(run).parameters:
                call_kwargs["dependencies"] = AutomaticOptimizationDependencies(
                    progress_callback=progress_callback,
                    quality_callback=quality_callback,
                )
            raw = run(source_text, **call_kwargs)
        return _coerce_result(raw)
    except Exception as exc:  # noqa: BLE001 - UI boundary must not leak provider errors
        stage = str(st.session_state.get(_PROGRESS_LABEL_KEY, "初始化模型服务"))
        return FailedOptimization(
            code="optimization_failed",
            message=f"{_safe_error_message(exc)} 停止层级：{stage}",
        )


def _resume_context(
    result: AutomaticOptimizationResult | None,
    answers: Sequence[ClarificationAnswer] = (),
    clarification_reply: str | None = None,
    *,
    mode: str = "diagnose",
    skip_approval: bool | None = None,
    approval_token: str | None = None,
) -> AutomaticOptimizationContext:
    cache = result.research_cache if result is not None else None
    evidence = result.evidence_bundle if result is not None else None
    identity = _optional_identity()
    if result is not None:
        result_identity = _result_attr(result, "identity")
        if identity is None and isinstance(result_identity, ProductIdentity):
            identity = result_identity
    match result:
        case NeedsClarification():
            questions = result.questions
        case AwaitingApproval() | CompletedOptimization() | FailedOptimization() | None:
            questions = ()
    skip = _skip_approval_checked() if skip_approval is None else skip_approval
    common: dict[str, object] = {
        "clarification_answers": tuple(answers),
        "clarification_reply": clarification_reply,
        "clarification_questions": questions,
        "cached_research": cache,
        "cached_specialized_rules": (
            result.specialized_rule_cache if result is not None else None
        ),
        "auto_resolve_unverified": True,
        "mode": mode,
        "skip_approval": skip,
        "approval_token": approval_token,
        "identity": identity,
    }
    if result is not None and result.rule_context is not None:
        return AutomaticOptimizationContext(
            rule_context=result.rule_context,
            user_claims=evidence.user_claims if evidence is not None else (),
            suppressed_claim_terms=(
                evidence.suppressed_claim_terms if evidence is not None else ()
            ),
            allowed_keywords=evidence.allowed_keywords if evidence is not None else (),
            **common,  # type: ignore[arg-type]
        )
    return AutomaticOptimizationContext(**common)  # type: ignore[arg-type]


def _render_priority_issues(diagnosis: ListingDiagnosisReport) -> None:
    st.markdown("### 2. 主要问题")
    for level, title, expanded in (
        ("P0", "必须先修复", True),
        ("P1", "影响搜索与转化", False),
    ):
        rows = [issue for issue in diagnosis.issues if issue.level == level]
        if not rows:
            continue
        with st.expander(f"{level} · {title} · {len(rows)}项", expanded=expanded):
            for index, issue in enumerate(rows, start=1):
                st.markdown(f"**{index}. {issue.title}**")
                st.caption(issue.detail_zh)
    if not diagnosis.issues:
        st.caption("未定位优先问题。")


def _render_backend_diagnosis(diagnosis: ListingDiagnosisReport) -> None:
    st.markdown("### 3. Backend Search Terms 诊断")
    backend = diagnosis.backend
    st.caption(backend.summary_zh)
    if backend.terms:
        st.text(backend.terms)
    st.caption(
        f"{backend.bytes_used}/{backend.max_bytes} UTF-8 bytes · "
        f"{backend.token_count} tokens · 可见字段重复约 {backend.duplication_pct:.0f}%"
    )
    if backend.repeated_roots:
        st.caption("与可见字段重复词根：" + "、".join(backend.repeated_roots))
    if backend.incremental_roots:
        st.caption("增量词根：" + "、".join(backend.incremental_roots))
    if backend.uncovered_candidates:
        st.caption("相关性候选（非验证高流量）：" + "、".join(backend.uncovered_candidates))
    for note in backend.risk_notes_zh:
        st.caption(f"风险：{note}")


def _render_diagnosis_report(diagnosis: ListingDiagnosisReport) -> None:
    st.markdown("## 源稿诊断报告")
    source_label = "LLM 编辑评分" if diagnosis.scoring_source == "llm" else "规则评分"
    st.caption(f"{source_label} · 平均分 {diagnosis.average_score}/10")
    st.caption(diagnosis.disclaimer_zh)
    st.markdown("### 1. 字段检查")
    st.dataframe(
        [
            {
                "字段": row.field,
                "检查结果": row.metric,
                "状态": row.status,
                "说明": row.note_zh,
            }
            for row in diagnosis.field_checks
        ],
        hide_index=True,
        width="stretch",
    )
    _render_priority_issues(diagnosis)
    _render_backend_diagnosis(diagnosis)
    st.markdown("### 4. 十维评分")
    st.dataframe(
        [
            {
                "维度": score.label_zh,
                "得分": score.score,
                "主要依据": score.rationale_zh,
            }
            for score in diagnosis.scores
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(f"平均分：{diagnosis.average_score}/10")
    st.markdown("### 5. 建议处理顺序")
    for index, step in enumerate(diagnosis.fix_order, start=1):
        st.caption(f"{index}. {step}")


def _render_review_report(
    report: ListingReviewReport,
    *,
    heading: str,
    pending_count: int = 0,
) -> None:
    st.markdown(f"## {heading}")
    if pending_count:
        st.warning(f"待确认 · {pending_count}项", icon=":material/pending_actions:")
    elif report.status == "BLOCK":
        st.error("BLOCK · 必须先处理", icon=":material/block:")
    elif report.status == "WARN":
        st.warning("WARN · 建议先确认风险", icon=":material/warning:")
    else:
        st.success("PASS · 未发现阻断项", icon=":material/check_circle:")
    format_status = (
        "已通过" if pending_count and report.format_status == "PASS" else report.format_status
    )
    st.caption(f"格式状态：{format_status}")
    fact_status = "待确认" if pending_count else report.fact_status
    release_disposition = "clarify" if pending_count else report.release_disposition
    st.caption(f"事实状态：{fact_status}")
    release_label = _RELEASE_LABELS[release_disposition]
    st.caption(f"发布处置：{release_disposition}（{release_label}）")
    for severity in ("BLOCK", "WARN"):
        rows = [finding for finding in report.findings if finding.severity == severity]
        if not rows:
            continue
        with st.expander(f"{severity} · {len(rows)}项", expanded=severity == "BLOCK"):
            for finding in rows:
                st.text(f"{finding.field} · {finding.code}")
                st.caption(finding.message_zh)
                if finding.evidence_required:
                    st.caption("所需证据：" + finding.evidence_required)
    with st.expander("事实核查与证据优先级"):
        if report.resolved_facts:
            st.dataframe(
                [
                    {
                        "事实键": fact.key,
                        "确认值": fact.value,
                        "优先级": int(fact.source),
                        "SKU范围": fact.sku_scope,
                    }
                    for fact in report.resolved_facts
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("未提交结构化产品事实。性能、安全与兼容性宣称将按无证据处理。")
    with st.expander("关键词字段覆盖"):
        st.caption("仅判断文本相关性，不推断流量、排名、CTR或CVR。")
        st.dataframe(
            [
                {
                    "字段": row.field,
                    "已覆盖": "、".join(row.covered) or "—",
                    "未覆盖": "、".join(row.missing) or "—",
                }
                for row in report.keyword_coverage
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("10维独立评分"):
        score_note = "各维度独立评分，不计算平均总分。"
        if report.status != "PASS":
            score_note += " BLOCK不会被其他高分抵消。"
        st.caption(score_note)
        st.dataframe(
            [
                {
                    "维度": score.dimension,
                    "分数": score.score,
                    "依据": score.rationale_zh,
                }
                for score in report.scores
            ],
            hide_index=True,
            width="stretch",
        )


def _render_research_evidence(cache: AutomaticResearchCache) -> None:
    with st.expander("安全的 MCP / 市场研究依据", expanded=False):
        sections = format_mcp_research_sections(cache.snapshots)
        if sections:
            for title, lines in sections:
                st.text(title)
                for line in lines:
                    st.caption(line)
        else:
            st.caption("未连接市场数据源；没有市场事实进入优化。")
        bundle = cache.bundle
        if bundle.allowed_keywords:
            st.caption("允许的研究关键词：" + "、".join(bundle.allowed_keywords))
        if bundle.items:
            st.caption(f"已接收 {len(bundle.items)} 条经过筛选的研究项（优先级6）。")
        if bundle.gaps:
            st.caption("研究缺口：" + "、".join(gap.code for gap in bundle.gaps))


def _render_evidence(
    result: RenderableOptimization,
) -> None:
    if result.research_cache is not None:
        _render_research_evidence(result.research_cache)
    render_specialized_evidence(result)


def _render_audit_layers_panel() -> None:
    layers = layers_from_session(st.session_state.get("audit_layers"))
    if not layers:
        return
    st.markdown("### 兼容审计")
    for title, lines in format_layer_sections(layers):
        with st.expander(title, expanded=title.strip().startswith("L4")):
            for line in lines:
                st.caption(line)


_FUNNEL_STAGE_LABELS = {
    "exposure": "曝光",
    "ctr": "点击率 CTR",
    "cvr": "转化率 CVR",
    "cart_to_purchase": "加购→购买",
}


def _render_identity_strip(result: object) -> None:
    identity = _result_attr(result, "identity")
    if identity is None:
        return
    asin = getattr(identity, "asin", None)
    marketplace = getattr(identity, "marketplace", None)
    product_type = getattr(identity, "product_type", None)
    parts = [part for part in (asin, marketplace, product_type) if part]
    if not parts:
        return
    st.caption("产品身份（展示用，非事实权威）：" + " · ".join(str(part) for part in parts))


def _render_funnel_hypotheses(result: object) -> None:
    hypotheses = _result_attr(result, "funnel_hypotheses", ()) or ()
    if not hypotheses:
        return
    st.markdown("### 漏斗假设（文案侧）")
    st.caption("无 CTR/CVR 实绩数据时仅为假设，不能定位真实漏斗根因。")
    for hypothesis in hypotheses:
        stage = getattr(hypothesis, "stage", "")
        label = _FUNNEL_STAGE_LABELS.get(str(stage), str(stage))
        confidence = getattr(hypothesis, "confidence", "low")
        note = getattr(hypothesis, "note_zh", "")
        st.markdown(f"**{label}** · 置信度 {confidence}")
        st.caption(str(note))


def _render_awaiting_approval(
    source_text: str,
    result: AwaitingApproval,
    progress_callback: Callable[[str, int, int], None] | None = None,
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None,
) -> None:
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        st.info("Stage 1 诊断完成。请审阅侧栏报告后生成上传稿。", icon=":material/analytics:")
        _render_identity_strip(result)
        _render_funnel_hypotheses(result)
        diagnosis = _result_attr(result, "diagnosis_report")
        if diagnosis is not None:
            average = getattr(diagnosis, "average_score", None)
            if average is not None:
                st.caption(f"编辑评分平均 {average}/10 · 详细报告见侧栏")
        if st.button(
            "生成上传稿",
            type="primary",
            key="generate_upload_draft",
            icon=":material/upload_file:",
        ):
            token = str(
                _result_attr(result, "approval_token", "")
                or st.session_state.get(_APPROVAL_TOKEN_KEY, "")
            )
            context = _resume_context(
                result,
                mode="optimize",
                skip_approval=False,
                approval_token=token or None,
            )
            next_result = _invoke_automatic(
                source_text,
                context,
                spinner_text="正在生成并门禁校验上传稿…（约 15–60 秒）",
                progress_callback=progress_callback,
                quality_callback=quality_callback,
            )
            _store_result(next_result)
            st.rerun()
        st.caption("改动上方 Listing 后需重新分析；审批令牌会失效。")


def _render_completed(result: CompletedOptimization) -> None:
    postflight = _result_attr(result, "postflight_review")
    postflight_status = getattr(postflight, "status", None)
    can_optimize = getattr(postflight, "can_optimize", True)
    if postflight_status == "BLOCK" or not can_optimize:
        st.error("优化后复核 BLOCK，已禁止进入复制区。", icon=":material/block:")
        return
    rendered = _result_attr(result, "rendered_text", "")
    if isinstance(rendered, str) and rendered and not st.session_state.get(_OPTIMIZED_WIDGET_KEY):
        st.session_state[_OPTIMIZED_WIDGET_KEY] = rendered
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        st.success("优化完成，发布门槛通过。", icon=":material/check_circle:")
        _render_identity_strip(result)
        st.text_area(
            "优化后 Listing",
            height=420,
            key=_OPTIMIZED_WIDGET_KEY,
        )
        st.caption("可编辑；在框内全选（Ctrl+A）后复制。")


def _render_failed(
    source_text: str,
    result: FailedOptimization,
    progress_callback: Callable[[str, int, int], None] | None = None,
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None,
) -> AutomaticOptimizationResult:
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        st.error(result.message, icon=":material/error:")
        st.caption(f"错误代码：{result.code}")
        last_candidate_text = _result_attr(result, "last_candidate_text", "")
        if isinstance(last_candidate_text, str) and last_candidate_text.strip():
            st.warning(
                "以下是最后一轮生成稿，但质量门禁未全部通过，不可直接发布。",
                icon=":material/warning:",
            )
            st.text_area(
                "最后一轮稿件（未通过）",
                value=last_candidate_text,
                height=420,
                disabled=False,
                key="failed_last_candidate",
            )
            failures = _result_attr(result, "quality_failures", ())
            if isinstance(failures, (list, tuple)) and failures:
                with st.expander("最后一轮失败原因", expanded=True):
                    for failure in failures:
                        st.text(f"• {failure}")
        if result.code == "invalid_source":
            st.caption("请在下方输入框提交缩短后的 Listing。")
            return result
        if result.code == "stale_approval":
            st.caption("请重新粘贴/发送当前 Listing 做 Stage 1 分析。")
            return result
        if st.button("重试", type="secondary", key="automatic_retry"):
            retry = _invoke_automatic(
                source_text,
                _resume_context(result, mode="diagnose", skip_approval=_skip_approval_checked()),
                progress_callback=progress_callback,
                quality_callback=quality_callback,
            )
            _store_result(retry)
            st.rerun()
    return result


def _render_result(
    source_text: str,
    result: AutomaticOptimizationResult,
    progress_callback: Callable[[str, int, int], None] | None = None,
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None,
) -> None:
    # Branch on status string — class identity can break after Streamlit hot reload.
    status = str(_result_attr(result, "status", ""))
    if status == "completed":
        if isinstance(result, CompletedOptimization):
            _render_completed(result)
        else:
            rebuilt = _coerce_result(_result_payload(result) or {})
            if isinstance(rebuilt, CompletedOptimization):
                _render_completed(rebuilt)
            else:
                st.warning("结果已过期，请重新提交 Listing。")
        return
    if status == "awaiting_approval":
        if isinstance(result, AwaitingApproval):
            _render_awaiting_approval(
                source_text, result, progress_callback, quality_callback
            )
        else:
            rebuilt = _coerce_result(_result_payload(result) or {})
            if isinstance(rebuilt, AwaitingApproval):
                _render_awaiting_approval(
                    source_text, rebuilt, progress_callback, quality_callback
                )
            else:
                st.warning("诊断状态已过期，请重新提交 Listing。")
        return
    if status == "needs_clarification":
        if isinstance(result, NeedsClarification):
            render_clarification(result)
        else:
            rebuilt = _coerce_result(_result_payload(result) or {})
            if isinstance(rebuilt, NeedsClarification):
                render_clarification(rebuilt)
            else:
                st.warning("澄清状态已过期，请重新提交 Listing。")
        return
    if status == "failed":
        if isinstance(result, FailedOptimization):
            _render_failed(source_text, result, progress_callback, quality_callback)
        else:
            rebuilt = _coerce_result(_result_payload(result) or {})
            if isinstance(rebuilt, FailedOptimization):
                _render_failed(
                    source_text, rebuilt, progress_callback, quality_callback
                )
            else:
                st.error("自动优化未完成，请稍后重试。")
        return
    st.warning("无法识别的结果状态，请点击「新建对话」后重试。")


def _render_sidebar(result: AutomaticOptimizationResult | None) -> None:
    with st.sidebar:
        st.markdown("## 审核层")
        st.caption("默认两阶段：先诊断审批，再生成可复制终稿。")
        if st.button("新建对话", icon=":material/add_comment:", width="stretch"):
            _clear_workflow_state()
            st.rerun()
        st.text_input(
            "可选 ASIN（仅身份展示）",
            key=_ASIN_KEY,
            max_chars=10,
            placeholder="例如 B0XXXXXXXX",
            help="不会从标题猜测 ASIN；留空可只贴文案运行。",
        )
        asin_raw = st.session_state.get(_ASIN_KEY, "")
        if isinstance(asin_raw, str) and asin_raw.strip() and not _ASIN_RE.fullmatch(
            asin_raw.strip()
        ):
            st.caption("ASIN 须为 10 位字母数字，当前输入无效（已忽略）。")
        st.checkbox(
            "跳过诊断，直接优化",
            key=_SKIP_APPROVAL_KEY,
            help="兼容旧的一键到底体验；默认关闭。",
        )
        st.markdown("### 流程与路由")
        if result is None:
            st.caption("等待 Listing 输入")
            return
        status = str(_result_attr(result, "status", "unknown"))
        status_color = {
            "awaiting_approval": "blue",
            "completed": "green",
            "failed": "red",
            "needs_clarification": "orange",
        }.get(status, "orange")
        st.badge(status, icon=":material/progress_activity:", color=status_color)
        _render_identity_strip(result)
        rule_context = _result_attr(result, "rule_context")
        if rule_context is not None:
            marketplace = getattr(rule_context, "marketplace", None)
            product_type = getattr(rule_context, "product_type", None)
            if marketplace and product_type:
                st.caption(f"{marketplace} · {product_type}")
        if status == "awaiting_approval":
            _render_funnel_hypotheses(result)
        diagnosis = _result_attr(result, "diagnosis_report")
        source_review = _result_attr(result, "source_review")
        postflight_review = _result_attr(result, "postflight_review")
        if diagnosis is not None and status != "completed":
            # Stage1 / clarify: full diagnosis. Completed keeps compact source summary below.
            _render_diagnosis_report(diagnosis)  # type: ignore[arg-type]
        if source_review is not None:
            questions = _result_attr(result, "questions", ())
            if status == "completed":
                # Historical source BLOCK/WARN must not look like a live gate failure.
                st.markdown("## 原始 Listing 审核")
                st.success(
                    "原始问题已由优化稿处理，当前状态以优化后审核为准。",
                    icon=":material/check_circle:",
                )
                format_status = getattr(source_review, "format_status", "—")
                release_disposition = getattr(source_review, "release_disposition", "release")
                release_label = _RELEASE_LABELS.get(str(release_disposition), str(release_disposition))
                st.caption(f"原始格式状态：{format_status}")
                st.caption("原始事实状态：已解决")
                st.caption(f"原始发布处置：{release_disposition}（{release_label}）")
            elif status == "needs_clarification" and postflight_review is not None:
                st.markdown("## 原始 Listing 审核")
                st.info(
                    "原始阶段检查已完成，整体流程仍有待确认项。",
                    icon=":material/pending_actions:",
                )
                st.caption("原始阶段状态：已完成，等待当前问题关闭")
            elif diagnosis is None or status == "needs_clarification":
                source_pending = (
                    len(questions)  # type: ignore[arg-type]
                    if status == "needs_clarification" and postflight_review is None
                    else 0
                )
                _render_review_report(
                    source_review,  # type: ignore[arg-type]
                    heading="原始 Listing 审核",
                    pending_count=source_pending,
                )
            elif status == "awaiting_approval":
                format_status = getattr(source_review, "format_status", "—")
                st.caption(f"原始格式状态：{format_status} · 终稿以优化后审核门禁为准。")
        _render_evidence(result)
        if postflight_review is not None:
            questions = _result_attr(result, "questions", ())
            postflight_pending = len(questions) if status == "needs_clarification" else 0  # type: ignore[arg-type]
            _render_review_report(
                postflight_review,  # type: ignore[arg-type]
                heading="优化后审核（发布门禁）",
                pending_count=postflight_pending,
            )
        _render_audit_layers_panel()


def _invalid_input_result() -> AutomaticOptimizationResult:
    return _coerce_result(FailedOptimization(code="invalid_source", message=""))


def _handle_prompt(
    prompt: str,
    result: AutomaticOptimizationResult | None,
    source_text: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
    quality_callback: Callable[[int, int, tuple[str, ...], bool], None] | None = None,
) -> None:
    status = str(_result_attr(result, "status", "")) if result is not None else ""
    if status == "needs_clarification" and result is not None:
        try:
            require_clarification_input(prompt)
        except InputSecurityError:
            _store_result(_invalid_input_result())
            return
        replies = TypeAdapter(tuple[str, ...]).validate_python(
            st.session_state.get(_CLARIFICATION_REPLIES_KEY, ())
        )
        st.session_state[_CLARIFICATION_REPLIES_KEY] = (*replies, prompt)
        # Clarification is orthogonal to the control plane:
        # - source-fact pause (no postflight yet) → stay on Stage1 diagnose
        # - postflight pause or skip-approval → re-enter generation
        # - Stage1 already issued a token → Stage2 optimize with that token
        postflight = _result_attr(result, "postflight_review")
        stored_token = st.session_state.get(_APPROVAL_TOKEN_KEY)
        token = stored_token if isinstance(stored_token, str) and stored_token else None
        if _skip_approval_checked():
            resume_mode = "optimize"
            resume_skip = True
            resume_token = None
        elif postflight is not None:
            # Postflight questions only exist after Stage2 generation.
            resume_mode = "optimize"
            resume_skip = token is None
            resume_token = token
        elif token:
            resume_mode = "optimize"
            resume_skip = False
            resume_token = token
        else:
            resume_mode = "diagnose"
            resume_skip = False
            resume_token = None
        context = _resume_context(
            result,
            clarification_reply=prompt,
            mode=resume_mode,
            skip_approval=resume_skip,
            approval_token=resume_token,
        )
        _store_result(
            _invoke_automatic(
                source_text,
                context,
                progress_callback=progress_callback,
                quality_callback=quality_callback,
            )
        )
        return
    # New listing (or retry after completed/failed/empty/awaiting state).
    _clear_workflow_state()
    try:
        require_listing_input(prompt)
    except InputSecurityError:
        _store_result(_invalid_input_result())
        return
    st.session_state[_SOURCE_TEXT_KEY] = prompt
    _sync_source_fingerprint(prompt)
    _store_result(
        _invoke_automatic(
            prompt,
            progress_callback=progress_callback,
            quality_callback=quality_callback,
        )
    )


# Bump whenever terminal-result semantics change. This invalidates stale
# per-tab failures produced by the previous five-round language gate.
_RESULT_SCHEMA_VERSION = "control_plane_v5_rule_aware_five_point_output"


def render_app() -> None:
    """Render the single automatic Streamlit workflow."""
    st.set_page_config(
        page_title="Amazon 文案优化器",
        page_icon=":material/edit_note:",
        layout="wide",
        initial_sidebar_state="auto",
    )
    # Drop session results produced before control-plane states / after hot reload.
    if st.session_state.get("_result_schema_version") != _RESULT_SCHEMA_VERSION:
        st.session_state.pop(_RESULT_KEY, None)
        st.session_state.pop(_OPTIMIZED_WIDGET_KEY, None)
        st.session_state.pop(_APPROVAL_TOKEN_KEY, None)
        st.session_state["_result_schema_version"] = _RESULT_SCHEMA_VERSION
    # Recover source text still present in the chat widget after a partial crash.
    if not st.session_state.get(_SOURCE_TEXT_KEY):
        widget_value = st.session_state.get(_SOURCE_WIDGET_KEY)
        if isinstance(widget_value, str) and widget_value.strip():
            st.session_state[_SOURCE_TEXT_KEY] = widget_value.strip()
    _inject_theme_styles()
    eyebrow = (
        '<div class="lithos-eyebrow">'
        '<span class="lithos-eyebrow-clause">AMAZON COPY OPTIMIZER</span>'
        '<span class="lithos-eyebrow-clause">DIAGNOSE FIRST, THEN OPTIMIZE</span>'
        "</div>"
    )
    st.markdown(
        eyebrow,
        unsafe_allow_html=True,
    )
    st.markdown('<h1 class="lithos-title">文案诊断与安全改写</h1>', unsafe_allow_html=True)
    subtitle = """<p class="lithos-sub">
      <span class="lithos-sub-unit">粘贴完整 Listing</span>，<wbr>
      <span class="lithos-sub-unit">先出诊断与漏斗假设</span>，<wbr>
      <span class="lithos-sub-unit">你确认后再生成可复制上传稿。</span>
    </p>"""
    st.markdown(
        subtitle,
        unsafe_allow_html=True,
    )
    source_text = _SOURCE_TEXT_ADAPTER.validate_python(st.session_state.get(_SOURCE_TEXT_KEY, ""))
    result = _stored_result()
    _render_sidebar(result)
    chat_column, runtime_column, quality_column = st.columns(
        [2.15, 0.9, 1.15], gap="large"
    )
    with runtime_column:
        runtime_slot = st.empty()
        _render_runtime_panel(runtime_slot, result)
    progress_callback = _progress_callback(runtime_slot, result)
    with quality_column:
        quality_slot = st.empty()
        _render_quality_rounds_panel(quality_slot)
    quality_callback = _quality_callback(quality_slot)
    with chat_column:
        if not source_text:
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                st.markdown("发送完整 Listing，我会先诊断再请你确认生成。")
                st.caption("可选填 ASIN（仅展示）。支持勾选「跳过诊断，直接优化」。")
        else:
            with st.chat_message("user", avatar=":material/person:"):
                st.code(source_text, language=None, wrap_lines=True)
            replies = TypeAdapter(tuple[str, ...]).validate_python(
                st.session_state.get(_CLARIFICATION_REPLIES_KEY, ())
            )
            for reply in replies:
                with st.chat_message("user", avatar=":material/person:"):
                    st.markdown(reply)
        if result is not None:
            _render_result(
                source_text,
                result,
                progress_callback,
                quality_callback,
            )
    result_status = str(_result_attr(result, "status", "")) if result is not None else ""
    placeholder = (
        "回复确认结果；无法确认可写“删除”"
        if result_status == "needs_clarification"
        else "粘贴完整 Listing，或开始下一份 Listing"
    )
    prompt = st.chat_input(
        placeholder,
        key=_SOURCE_WIDGET_KEY,
        submit_mode="disable",
        max_chars=MAX_LISTING_INPUT_CHARS,
    )
    if prompt:
        # Persist the pasted listing immediately so a refresh still shows context.
        if result is None or str(_result_attr(result, "status", "")) != "needs_clarification":
            st.session_state[_SOURCE_TEXT_KEY] = prompt
        status_label = (
            "处理中：研究 → 诊断"
            if not _skip_approval_checked()
            else "处理中：研究 → 诊断 → 改写 → 门禁"
        )
        with st.status(status_label, expanded=True) as status_box:
            status_box.write("已接收 Listing，开始处理…")
            _handle_prompt(
                prompt,
                result,
                source_text,
                progress_callback,
                quality_callback,
            )
            status_box.update(label="处理完成", state="complete")
        st.rerun()


if __name__ == "__main__":
    render_app()
