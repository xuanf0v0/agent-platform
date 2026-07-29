export interface BulletDeliverable {
  text: string;
  text_zh: string;
}

export interface ShoppingQuestion {
  question: string;
  answer_basis: string;
  answer_zh: string;
}

export interface PlusModule {
  module: string;
  purpose: string;
  content: string;
}

export interface CategoryRecommendation {
  path: string;
  node_id_path: string;
  basis: string;
  verification: string;
}

export interface Deliverable {
  title: string;
  title_zh: string;
  title_chars: number;
  item_highlights: string;
  item_highlights_zh: string;
  item_highlights_chars: number;
  bullets: BulletDeliverable[];
  search_terms: string;
  search_terms_bytes: number;
  product_description: string;
  product_description_zh: string;
  shopping_questions: ShoppingQuestion[];
  a_plus_modules: PlusModule[];
  keyword_intent_map: Record<string, string[]>;
  category_recommendations: CategoryRecommendation[];
  claim_evidence_map: Array<{ claim: string; source: string; status: string }>;
  attribute_checklist: string[];
  compliance_notes: string[];
  unresolved: string[];
  policy_status: "PASS" | "WARN" | "BLOCK";
  policy_issues: string[];
}

export interface ImageBriefItem {
  image: string;
  selling_point: string;
  color_palette: string;
  product_angle: string;
  background: string;
  layout: string;
  detail_treatment: string;
  image_copy: string;
}

export interface ImageDesignPlan {
  task_type: string;
  research_basis: string[];
  source_analysis: string[];
  image_scores: Record<string, number>;
  images: ImageBriefItem[];
  upload_requests: string[];
  compliance_notes: string[];
}

export interface CreationSession {
  session_id: string;
  revision: number;
  stage: string;
  status: string;
  last_message_zh: string;
  artifacts: Record<string, { summary_zh: string; payload: Record<string, unknown>; approved: boolean }>;
  deliverable?: Deliverable | null;
  image_design_requested?: boolean | null;
  image_task_type: string;
  image_asset_count: number;
  image_design_plan?: ImageDesignPlan | null;
  human_review_confirmed: boolean;
  active_rule_files: string[];
  brief: {
    product_name: string;
    marketplace: string;
    brand: string;
    product_type: string;
    language: string;
    product_asin: string;
    specs_text: string;
    competitors: string[];
    sensitive_category: boolean;
    listing_scope: string;
    listing_scope_confirmed: boolean;
    media_category: boolean;
    media_status_confirmed: boolean;
  };
}
