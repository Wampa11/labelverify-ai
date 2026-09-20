/**
 * TypeScript contracts for image upload analysis (mirrors backend models).
 * Architectural responsibility: frontend types for Phase 2 image ingestion responses.
 */

export type QualityStatus = "GOOD" | "WARNING" | "POOR";

export type ImageFormat = "jpeg" | "png" | "webp";

export interface ImageValidationResult {
  accepted: boolean;
  detected_format: ImageFormat | null;
  declared_content_type: string | null;
  size_bytes: number;
  message: string;
}

export interface ImageMetadata {
  original_filename: string | null;
  format: ImageFormat;
  width_px: number;
  height_px: number;
  mode: string;
  size_bytes: number;
  exif_orientation_applied: boolean;
}

export interface QualityMeasurements {
  width_px: number;
  height_px: number;
  shortest_side_px: number;
  laplacian_variance: number;
  mean_brightness: number;
  contrast_std: number;
  near_black_fraction: number;
  near_white_fraction: number;
}

export interface ImageQualityAssessment {
  status: QualityStatus;
  measurements: QualityMeasurements;
  warnings: string[];
  notes: string;
}

export interface PreprocessingOperation {
  name: string;
  applied: boolean;
  detail: string;
}

export interface PreprocessingSummary {
  operations: PreprocessingOperation[];
  deskew_applied: boolean;
  deskew_angle_degrees: number | null;
  deskew_skipped_reason: string | null;
}

export interface ImageAnalysisResponse {
  analysis_id: string;
  validation: ImageValidationResult;
  metadata: ImageMetadata;
  quality: ImageQualityAssessment;
  preprocessing: PreprocessingSummary;
  display_image_base64: string;
  display_media_type: string;
  ocr_image_base64: string;
  ocr_media_type: string;
  processing_time_ms: number;
  stage_timings_ms: Record<string, number>;
  disclaimer: string;
}

export interface ImageUploadError {
  error: string;
  code: string;
}
