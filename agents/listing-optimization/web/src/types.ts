export type WorkflowStatus =
  | "awaiting_approval"
  | "needs_clarification"
  | "completed"
  | "failed";

export interface Question {
  code: string;
  question_zh: string;
  evidence_needed?: string;
}

export interface Finding {
  code?: string;
  title?: string;
  message?: string;
  detail_zh?: string;
  severity?: string;
}

export interface WorkflowResult {
  status: WorkflowStatus;
  approval_token?: string;
  rendered_text?: string;
  message?: string;
  questions?: Question[];
  source_review?: Record<string, unknown>;
  postflight_review?: Record<string, unknown>;
  diagnosis_report?: Record<string, unknown>;
  funnel_hypotheses?: Array<{ stage: string; confidence: string; note_zh: string }>;
  rule_context?: Record<string, unknown>;
  evidence_bundle?: Record<string, unknown>;
  research_cache?: Record<string, unknown>;
  specialized_rule_cache?: Record<string, unknown> | null;
}

export interface OptimizeContext {
  mode?: "diagnose" | "optimize";
  skip_approval?: boolean;
  approval_token?: string;
  clarification_reply?: string;
  clarification_questions?: Question[];
  cached_research?: Record<string, unknown>;
  cached_specialized_rules?: Record<string, unknown> | null;
  rule_context?: Record<string, unknown>;
  identity?: { asin?: string };
}

export type CopyWorkflow = "write" | "optimize" | "seo" | "analyze";
export interface CopyWorkflowState { workflow: CopyWorkflow; step: string; revision: number }
export interface CopyWorkflowView {
  state: CopyWorkflowState;
  route: string[];
  required_inputs: string[];
  completed: boolean;
}
