export interface Deliverable {
  title: string; title_zh: string; item_highlights: string; item_highlights_zh: string;
  bullets: Array<{ text: string; text_zh: string }>; search_terms: string;
  policy_status: "PASS" | "WARN" | "BLOCK"; policy_issues: string[];
}
export interface CreationSession {
  session_id: string; revision: number; stage: string; status: string; last_message_zh: string;
  artifacts: Record<string, { summary_zh: string; payload: Record<string, unknown>; approved: boolean }>;
  deliverable?: Deliverable | null; image_design_requested?: boolean | null;
  brief: { product_name: string; marketplace: string; brand: string; specs_text: string };
}
