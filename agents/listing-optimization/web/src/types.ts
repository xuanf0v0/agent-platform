export type Status = "awaiting_approval" | "needs_clarification" | "completed" | "failed";

export interface Question { code: string; question_zh: string; evidence_needed?: string }
export interface FunnelHypothesis { stage: string; confidence: string; note_zh: string; disclaimer_zh?: string }
export interface WorkflowResult {
  status: Status; approval_token?: string; rendered_text?: string; message?: string; code?: string;
  questions?: Question[]; diagnosis_report?: Record<string, unknown> | null;
  source_review?: Record<string, unknown> | null; postflight_review?: Record<string, unknown> | null;
  rule_context?: Record<string, unknown> | null; evidence_bundle?: Record<string, unknown> | null;
  research_cache?: Record<string, unknown> | null; specialized_rule_cache?: Record<string, unknown> | null;
  identity?: { asin?: string; marketplace?: string; product_type?: string; label?: string } | null;
  funnel_hypotheses?: FunnelHypothesis[]; quality_failures?: string[]; last_candidate_text?: string;
}
export interface OptimizeContext {
  mode?: "diagnose" | "optimize"; skip_approval?: boolean; approval_token?: string;
  clarification_reply?: string; clarification_questions?: Question[];
  cached_research?: Record<string, unknown> | null; cached_specialized_rules?: Record<string, unknown> | null;
  rule_context?: Record<string, unknown> | null; evidence_bundle?: Record<string, unknown> | null;
  user_claims?: unknown[]; suppressed_claim_terms?: string[]; allowed_keywords?: string[];
  identity?: { asin?: string };
}
