/**
 * TypeScript contracts for structured label extraction (mirrors backend models).
 * Architectural responsibility: frontend types for Phase 4 extraction responses.
 * ExtractionStatus is not regulatory PASS/REVIEW/FAIL.
 */

export type ExtractionStatus = "FOUND" | "UNCERTAIN" | "NOT_FOUND";

export type ExtractionMethod =
  | "regex"
  | "layout_heuristic"
  | "terminology_match"
  | "combined"
  | "not_extracted";

export interface OcrRegionRef {
  text: string;
  confidence: number | null;
  bounding_box: {
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
  } | null;
  provider_name: string | null;
  preprocessing_profile: string | null;
}

export interface ExtractedField {
  field_name: string;
  status: ExtractionStatus;
  raw_text: string | null;
  normalized_value: string | null;
  normalized_numeric: number | null;
  normalized_unit: string | null;
  candidates: string[];
  ocr_regions: OcrRegionRef[];
  extraction_method: ExtractionMethod;
  explanation: string;
  ai_fallback_hints: Record<string, unknown>;
}

export interface OcrPassSummary {
  profile: string;
  max_edge_px: number;
  provider_name: string;
  preprocessing_time_ms: number;
  ocr_time_ms: number;
  extraction_time_ms: number;
  total_pass_time_ms: number;
  ocr_text_preview: string;
  word_count: number;
  image_width_px: number | null;
  image_height_px: number | null;
  fields: Record<string, ExtractedField>;
  found_count: number;
  uncertain_count: number;
  not_found_count: number;
}

export interface RetryDecision {
  triggered: boolean;
  reasons: string[];
  performed: boolean;
}

export interface ResultSelection {
  selected_profile: string;
  reason: string;
  fast_score: number | null;
  enhanced_score: number | null;
}

export interface ExtractedLabelResult {
  analysis_id: string;
  selected_fields: Record<string, ExtractedField>;
  fast_pass: OcrPassSummary;
  enhanced_pass: OcrPassSummary | null;
  retry: RetryDecision;
  selection: ResultSelection;
  ocr_image_width_px: number | null;
  ocr_image_height_px: number | null;
  display_image_width_px: number | null;
  display_image_height_px: number | null;
  stage_timings_ms: Record<string, number>;
  processing_time_ms: number;
  disclaimer: string;
}

export interface LabelExtractionResponse {
  analysis_id: string;
  filename: string | null;
  display_image_base64: string;
  display_media_type: string;
  metadata_width_px: number;
  metadata_height_px: number;
  quality_status: string;
  quality_warnings: string[];
  extraction: ExtractedLabelResult;
  processing_time_ms: number;
  stage_timings_ms: Record<string, number>;
  disclaimer: string;
}

export const FIELD_DISPLAY_ORDER = [
  "brand_name",
  "class_type",
  "alcohol_content",
  "net_contents",
  "government_warning",
] as const;

export const FIELD_LABELS: Record<(typeof FIELD_DISPLAY_ORDER)[number], string> = {
  brand_name: "Brand Name",
  class_type: "Class / Type",
  alcohol_content: "Alcohol Content",
  net_contents: "Net Contents",
  government_warning: "Government Warning",
};
