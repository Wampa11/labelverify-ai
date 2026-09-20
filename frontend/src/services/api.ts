/**
 * HTTP client for LabelVerify AI backend endpoints.
 * Architectural responsibility: browser ↔ API communication without secrets.
 */
import type {
  BatchCreateResponse,
  BatchItemDetail,
  BatchJobStatus,
  BatchValidationResult,
} from "../types/batch";
import type { LabelExtractionResponse } from "../types/extraction";
import type { ImageAnalysisResponse, ImageUploadError } from "../types/imageAnalysis";
import type {
  ApplicationData,
  SingleReviewVerificationResponse,
} from "../types/verification";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

async function readUploadError(response: Response): Promise<{ message: string; code?: string }> {
  let message = `Request failed (${response.status}). Please try again.`;
  let code: string | undefined;
  try {
    const payload = (await response.json()) as { detail?: ImageUploadError | string };
    if (payload.detail && typeof payload.detail === "object") {
      message = payload.detail.error || message;
      code = payload.detail.code;
    }
  } catch {
    // Keep generic message when body is not JSON.
  }
  return { message, code };
}

/**
 * Upload one label image for validation and preprocessing.
 * Does not permanently store the file on the server.
 */
export async function analyzeLabelImage(file: File): Promise<ImageAnalysisResponse> {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${API_BASE}/api/v1/images/analyze`, {
    method: "POST",
    body,
  });

  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }

  return (await response.json()) as ImageAnalysisResponse;
}

/**
 * Upload one label image for OCR + structured field extraction.
 * Extraction is not a regulatory determination.
 */
export async function extractLabelFields(file: File): Promise<LabelExtractionResponse> {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${API_BASE}/api/v1/labels/extract`, {
    method: "POST",
    body,
  });

  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }

  return (await response.json()) as LabelExtractionResponse;
}

/**
 * Analyze a label image (label-only Single Review by default).
 * Optional application enables application-comparison mode (Batch / future COLA).
 */
export async function analyzeLabel(
  file: File,
  application?: ApplicationData | null,
): Promise<SingleReviewVerificationResponse> {
  const body = new FormData();
  body.append("file", file);
  if (application) {
    body.append("application", JSON.stringify(application));
  }

  const response = await fetch(`${API_BASE}/api/v1/verify`, {
    method: "POST",
    body,
  });

  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }

  return (await response.json()) as SingleReviewVerificationResponse;
}

/** @deprecated Prefer analyzeLabel — kept for call sites during Phase 8.5 transition. */
export async function verifyLabel(
  file: File,
  application?: ApplicationData | null,
): Promise<SingleReviewVerificationResponse> {
  return analyzeLabel(file, application);
}

/** Fetch backend health for local/dev diagnostics. */
export async function fetchHealth(): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`);
  }
  return (await response.json()) as Record<string, unknown>;
}

/** Validate CSV manifest + label images without starting processing. */
export async function validateBatch(
  manifest: File,
  images: File[],
): Promise<BatchValidationResult> {
  const body = new FormData();
  body.append("manifest", manifest);
  for (const file of images) {
    body.append("files", file);
  }
  const response = await fetch(`${API_BASE}/api/v1/batches/validate`, {
    method: "POST",
    body,
  });
  let payload: BatchValidationResult;
  try {
    payload = (await response.json()) as BatchValidationResult;
  } catch {
    throw new ApiRequestError(
      `Request failed (${response.status}). Please try again.`,
      response.status,
    );
  }
  if (!response.ok && response.status !== 400) {
    throw new ApiRequestError(
      "Unable to validate this batch. Check the manifest and images, then try again.",
      response.status,
    );
  }
  return payload;
}

/** Create and start a batch job. */
export async function createBatch(
  manifest: File,
  images: File[],
): Promise<BatchCreateResponse> {
  const body = new FormData();
  body.append("manifest", manifest);
  for (const file of images) {
    body.append("files", file);
  }
  const response = await fetch(`${API_BASE}/api/v1/batches`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    if (response.status === 400) {
      const validation = (await response.json()) as BatchValidationResult;
      throw new ApiRequestError(
        validation.issues[0]?.message ?? "Batch validation failed.",
        400,
        "batch_validation_failed",
      );
    }
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return (await response.json()) as BatchCreateResponse;
}

/** Poll batch status. */
export async function fetchBatchStatus(batchId: string): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE}/api/v1/batches/${batchId}`);
  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return (await response.json()) as BatchJobStatus;
}

/** Fetch one batch item detail (Single Review-equivalent payload). */
export async function fetchBatchItemDetail(
  batchId: string,
  itemId: string,
): Promise<BatchItemDetail> {
  const response = await fetch(`${API_BASE}/api/v1/batches/${batchId}/items/${itemId}`);
  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return (await response.json()) as BatchItemDetail;
}

/** Download batch results CSV. */
export async function downloadBatchExport(batchId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/batches/${batchId}/export`);
  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return response.blob();
}

/** Sample manifest URL for evaluators (synthetic demo data). */
export function sampleManifestUrl(): string {
  return `${API_BASE}/api/v1/batches/sample-manifest`;
}

/** Download Single Label Excel report from a completed verification payload. */
export async function downloadSingleExcelReport(
  result: SingleReviewVerificationResponse,
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/reports/single`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result),
  });
  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return response.blob();
}

/** Download Batch Excel report. */
export async function downloadBatchExcelReport(batchId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/reports/batches/${batchId}`);
  if (!response.ok) {
    const { message, code } = await readUploadError(response);
    throw new ApiRequestError(message, response.status, code);
  }
  return response.blob();
}

/**
 * Privacy-safe site-access telemetry (once per SPA load).
 * Never throws to callers — telemetry must not affect the UI.
 */
export async function recordSiteAccess(route: string = "app"): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/telemetry/access`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route }),
    });
    return response.ok;
  } catch {
    return false;
  }
}
