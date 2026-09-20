/**
 * Shared verification TypeScript contracts aligned with the backend result model.
 * Architectural responsibility: frontend types for explainable PASS/REVIEW/FAIL outcomes.
 */
import type { ExtractedLabelResult } from "./extraction";

/** Allowed outcomes for every verification check. */
export type CheckStatus = "PASS" | "REVIEW" | "FAIL";

/** How a check decision was produced (for explainability). */
export type DecisionMethod =
  | "deterministic_rule"
  | "fuzzy_match"
  | "normalized_comparison"
  | "confidence_policy"
  | "ai_assist"
  | "human_review_required"
  | "not_evaluated"
  | "pipeline_stub";

/** Where a detected label value came from. */
export interface DetectionSource {
  detector: string;
  raw_text?: string | null;
  bounding_box?: Record<string, unknown> | null;
  notes?: string | null;
}

/** Outcome of a single field or regulatory check. */
export interface FieldCheckResult {
  rule_id?: string | null;
  check_name: string;
  application_value?: string | null;
  detected_label_value?: string | null;
  expected_value?: string | null;
  normalized_application_value?: string | null;
  normalized_detected_value?: string | null;
  status: CheckStatus;
  confidence?: number | null;
  explanation: string;
  decision_method: DecisionMethod;
  reason_code?: string | null;
  ai_assist_eligible?: boolean;
  limitations?: string[];
  technical_details?: Record<string, unknown>;
  detection_source?: DetectionSource | null;
  processing_time_ms?: number | null;
  authoritative_sources?: string[];
}

/** Full result of verifying one label (optionally against an application). */
export interface VerificationResult {
  verification_id?: string | null;
  product_class: string;
  verification_mode?: string;
  overall_status: CheckStatus;
  checks: FieldCheckResult[];
  pass_count: number;
  review_count: number;
  fail_count: number;
  processing_time_ms: number;
  stage_timings_ms?: Record<string, number>;
  ai_used: boolean;
  ai_degraded: boolean;
  /** Observable evidence-recovery summary — never a regulatory decision. */
  ai_assist?: {
    attempted?: boolean;
    called?: boolean;
    provider_name?: string | null;
    model?: string | null;
    trigger_reason_codes?: string[];
    fields_requested?: string[];
    fields_updated?: string[];
    fields_proposed?: string[];
    merge_outcomes?: Record<string, string>;
    latency_ms?: number | null;
    outcome?: string;
    explanation?: string;
    status_before?: string | null;
    status_after?: string | null;
    evidence_changed?: boolean;
    ai_configured?: boolean;
    ai_eligible?: boolean;
    eligible_fields?: string[];
    ai_succeeded?: boolean;
    failure_category?: string | null;
    evidence_method?: string;
  } | null;
  degradation_notes: string[];
  disclaimer: string;
}

/** Application-side values supplied for comparison. */
export interface ApplicationData {
  brand_name: string;
  class_type: string;
  alcohol_content_abv: string;
  net_contents: string;
  notes?: string | null;
}

/** Combined Single Review verification response. */
export interface SingleReviewVerificationResponse {
  analysis_id: string;
  verification_id: string;
  filename: string | null;
  /** label_only (Single Review) or application_comparison (Batch). */
  verification_mode?: "label_only" | "application_comparison" | string;
  application?: ApplicationData | null;
  display_image_base64: string;
  display_media_type: string;
  metadata_width_px: number;
  metadata_height_px: number;
  quality_status: string;
  quality_warnings: string[];
  extraction: ExtractedLabelResult;
  verification: VerificationResult;
  processing_time_ms: number;
  stage_timings_ms?: Record<string, number>;
  disclaimer: string;
}
