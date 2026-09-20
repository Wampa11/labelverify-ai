/**
 * Batch Review TypeScript contracts aligned with backend batch models.
 * Architectural responsibility: frontend types for batch orchestration (not regulatory rules).
 */
import type { SingleReviewVerificationResponse } from "./verification";

export type BatchItemProcessingState = "QUEUED" | "PROCESSING" | "COMPLETED" | "ERROR";
export type BatchJobState = "VALIDATED" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface BatchValidationIssue {
  code: string;
  message: string;
  filename?: string | null;
  row_number?: number | null;
}

export interface BatchValidationResult {
  valid: boolean;
  row_count: number;
  image_count: number;
  matched_count: number;
  missing_count: number;
  unreferenced_count: number;
  issues: BatchValidationIssue[];
}

export interface BatchItemSummary {
  item_id: string;
  filename: string;
  processing_state: BatchItemProcessingState;
  overall_status: string | null;
  brand_name: string;
  class_type: string;
  alcohol_content: string;
  net_contents: string;
  ai_assisted: boolean;
  processing_time_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  review_reason_codes: string[];
}

export interface BatchSummaryCounts {
  total: number;
  completed: number;
  pass_count: number;
  review_count: number;
  fail_count: number;
  error_count: number;
  queued_count: number;
  processing_count: number;
  ai_assisted_count: number;
  ai_budget_exhausted: boolean;
  ai_calls_used: number;
}

export interface BatchJobStatus {
  batch_id: string;
  state: BatchJobState;
  summary: BatchSummaryCounts;
  items: BatchItemSummary[];
  elapsed_ms: number | null;
  median_item_ms: number | null;
  p95_item_ms: number | null;
  concurrency: number;
  ai_budget_max: number;
  message: string | null;
  validation: BatchValidationResult | null;
}

export interface BatchCreateResponse {
  batch_id: string;
  state: BatchJobState;
  summary: BatchSummaryCounts;
  concurrency: number;
  message: string;
}

export interface BatchItemDetail {
  item_id: string;
  filename: string;
  processing_state: BatchItemProcessingState;
  error_code: string | null;
  error_message: string | null;
  result: SingleReviewVerificationResponse | null;
}
